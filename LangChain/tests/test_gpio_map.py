"""Generic wiring-map mechanisms; never firmware answers or hardware acceptance."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from hardware_claw.catalog import KnowledgeCatalog, CatalogError
from hardware_claw.projects.gpio_map import build_gpio_map, render_markdown
from hardware_claw.projects.service import ProjectService, ROOT
from hardware_claw.tools.project_tools import make_project_tools

BOARD = 'esp32_s3_devkitc1_n32r16v'


def state_for(parts, wires):
    catalog = KnowledgeCatalog()
    hardware = {'mcu': catalog.get(BOARD, include_shared=True)}
    hardware.update({instance: catalog.get(ident) for instance, ident in parts.items()})
    design = {'board_id': BOARD, 'components': [{'instance_id': k, 'hardware_id': v} for k,v in parts.items()],
              'connections': [{'a': a, 'b': b} for a,b in wires], 'pin_defines': {}}
    diagram = {'version': 1, 'parts': [{'id': k, 'type': h['upstream_definition']['type'], 'attrs': {}}
                                     for k,h in hardware.items()],
               'connections': [[a,b,'green',[]] for a,b in wires]}
    return {'project_id': 'software-fixture', 'version': 3, 'design_version': 1, 'files_design_version': 1,
            'design': design, 'hardware': hardware, 'files': {'diagram.json': json.dumps(diagram)}}


class GPIOMapTests(unittest.TestCase):
    def test_real_mapping_aliases_signals_and_unused_exclusion(self):
        state = state_for({'pot': 'potentiometer', 'motor': 'sg90_180'}, [
            ('mcu:1', 'pot:SIG'), ('mcu:4', 'motor:PWM'), ('mcu:3V3.1', 'pot:VCC'),
            ('mcu:GND.1','pot:GND'), ('mcu:TX','$serialMonitor:RX'), ('mcu:RX','$serialMonitor:TX')])
        state['design']['pin_defines'] = {'POT_PIN': 1, 'UNUSED': 12}
        original = copy.deepcopy(state)
        result = build_gpio_map(state)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual([r['gpio'] for r in result['rows']], [1, 4, 43, 44])
        self.assertEqual(result['rows'][0]['pin_defines'], ['POT_PIN'])
        self.assertEqual(result['rows'][1]['connected_to'][0]['signals'], ['CONTROL'])
        self.assertEqual(result['rows'][2]['board_pins'], ['TX'])
        self.assertIn('reserve_uart0_gpio', result['rows'][2]['board_policy_notes'])
        self.assertEqual(state, original)
        self.assertEqual(build_gpio_map(state), result)
        self.assertIn('GPIO 接线表', render_markdown(result))

    def test_shared_net_retains_all_destinations_without_false_conflict(self):
        state = state_for({'a':'mpu6050', 'b':'ds1307'}, [
            ('mcu:8','a:SDA'), ('a:SDA','b:SDA'), ('mcu:9','a:SCL'), ('a:SCL','b:SCL')])
        result = build_gpio_map(state)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual({d['endpoint'] for d in result['rows'][0]['connected_to']}, {'a:SDA','b:SDA'})
        self.assertEqual([r['gpio'] for r in result['rows']], [8, 9])

    def test_does_not_traverse_component_internals(self):
        state = state_for({'pot': 'potentiometer'}, [('mcu:4','res:1'), ('res:2','pot:SIG')])
        # Software-only resistor metadata, not a new production hardware card.
        state['hardware']['res'] = {'summary': {'id': 'fixture_resistor', 'kind':'passive'},
            'upstream_definition': {'type':'wokwi-resistor','pins':['1','2']}, 'profile': {}}
        diagram = json.loads(state['files']['diagram.json'])
        diagram['parts'].append({'id':'res','type':'wokwi-resistor','attrs':{}})
        state['files']['diagram.json'] = json.dumps(diagram)
        result = build_gpio_map(state)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual([d['endpoint'] for d in result['rows'][0]['connected_to']], ['res:1'])

    def test_unknown_endpoint_is_reported_and_not_guessed(self):
        state = state_for({'pot':'potentiometer'}, [('mcu:999','pot:SIG')])
        result = build_gpio_map(state)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['rows'], [])
        self.assertIn('mcu:999', result['unmapped_board_endpoints'])

    def test_source_failure_cannot_fallback_to_numeric_pin_name(self):
        state = state_for({'pot':'potentiometer'}, [('mcu:1','pot:SIG')])
        catalog = Mock()
        catalog._json.side_effect = CatalogError('SOURCE_CHANGED','fixture changed hash')
        result = build_gpio_map(state, catalog)
        self.assertEqual(result['rows'], [])
        self.assertIn('SOURCE_CHANGED', {i['code'] for i in result['issues']})

    def test_board_adapter_uses_source_targets_not_esp32_constants(self):
        state = state_for({'pot':'potentiometer'}, [('mcu:D2','pot:SIG')])
        state['hardware']['mcu']['upstream_definition']['pins'] = ['D2']
        state['hardware']['mcu']['upstream_definition']['type'] = 'board-fixture'
        diagram = json.loads(state['files']['diagram.json'])
        diagram['parts'][0]['type'] = 'board-fixture'
        state['files']['diagram.json'] = json.dumps(diagram)
        catalog = Mock()
        catalog._json.return_value = ({'pins':{'D2':{'target':'GPIO17'}}}, {'ref':'fixture/board.json','sha256':'a'*64})
        result = build_gpio_map(state, catalog)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['rows'][0]['gpio'], 17)

    def test_mismatched_diagram_uses_actual_wiring_and_marks_partial(self):
        state = state_for({'pot':'potentiometer'}, [('mcu:1','pot:SIG')])
        diagram = json.loads(state['files']['diagram.json'])
        diagram['connections'][0][0] = 'mcu:2'
        state['files']['diagram.json'] = json.dumps(diagram)
        result = build_gpio_map(state)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['rows'][0]['gpio'], 2)
        self.assertIn('CONNECTION_MISMATCH', {i['code'] for i in result['issues']})
        state['design_version'] = 2
        self.assertIn('STALE_DESIGN', {i['code'] for i in build_gpio_map(state)['issues']})

    def test_part_type_mismatch_does_not_attribute_known_signal(self):
        state = state_for({'pot':'potentiometer'}, [('mcu:1','pot:SIG')])
        diagram = json.loads(state['files']['diagram.json'])
        diagram['parts'][1]['type'] = 'another-part'
        state['files']['diagram.json'] = json.dumps(diagram)
        result = build_gpio_map(state)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['rows'][0]['connected_to'][0]['signals'], [])

    def test_malformed_diagram_has_no_partial_fabricated_rows(self):
        state = state_for({}, [])
        for text in ('[]', '{', '{"version":1,"version":1}',
                     '{"version":1,"parts":[],"connections":[["mcu",1,"",[]]]}'):
            with self.subTest(text=text):
                state['files']['diagram.json'] = text
                result = build_gpio_map(state)
                self.assertEqual(result['status'], 'unavailable')
                self.assertEqual(result['rows'], [])
                self.assertEqual(result['issues'][0]['code'], 'INVALID_DIAGRAM')

    def test_empty_diagram_and_missing_diagram_are_distinct(self):
        state = state_for({}, [])
        self.assertEqual(build_gpio_map(state)['status'], 'ready')
        state['files'] = {}
        self.assertEqual(build_gpio_map(state)['status'], 'unavailable')

    def test_multi_board_rows_are_qualified(self):
        state = state_for({}, [('mcu:TX','other:RX')])
        state['hardware']['other'] = copy.deepcopy(state['hardware']['mcu'])
        diagram = json.loads(state['files']['diagram.json'])
        diagram['parts'].append({'id':'other','type':'board-esp32-s3-devkitc-1'})
        state['files']['diagram.json'] = json.dumps(diagram)
        result = build_gpio_map(state)
        self.assertEqual([(r['board_instance'],r['gpio']) for r in result['rows']], [('mcu',43),('other',44)])
        self.assertEqual(result['rows'][1]['connected_to'][0]['endpoint'], 'mcu:TX')


class GPIOMapToolTests(unittest.TestCase):
    def setUp(self):
        base = ROOT/'temp/gpio-map-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.p = ProjectService.create('fixture','wire inventory mechanism','vscode',workspace=Path(self.tmp.name))
        self.tools = {t.name:t for t in make_project_tools(self.p)}
        state = state_for({'pot':'potentiometer'}, [('mcu:1','pot:SIG')])
        self.design = state['design'] | {'goal':'fixture','simulation_only':True, 'dependencies':[], 'assumptions':[]}

    def test_tools_return_and_refresh_host_owned_table_without_source_changes(self):
        self.tools['update_project_design'].invoke({'expected_version':0,'design':self.design})
        response = self.tools['scaffold_project'].invoke({'expected_version':1})
        self.assertEqual(response['execution_status'], 'ok')
        generated = response['data']['gpio_map']
        self.assertEqual(generated['status'], 'ready')
        self.assertEqual([r['gpio'] for r in generated['rows']], [1,43,44])
        self.assertTrue(Path(generated['artifacts']['markdown']).is_file())
        original_report = Path(generated['artifacts']['json']).read_bytes()
        before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.p.files.iterdir()}
        result = self.tools['get_project'].invoke({})
        self.assertEqual(result['data']['version'], 2)
        self.assertEqual(before, {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.p.files.iterdir()})
        self.assertEqual(self.tools['check_project_files'].invoke({})['data']['gpio_map']['status'], 'ready')
        # A valid map does not hide missing firmware/README in the file check.
        self.assertEqual(self.p.get()['file_check']['verdict'], 'fail')
        changed = json.loads(self.p.read_file('diagram.json')['content'])
        next(e for e in changed['connections'] if e[0]=='mcu:1')[0]='mcu:2'
        written = self.tools['write_project_files'].invoke({'expected_version':2,'files':{'diagram.json':json.dumps(changed)}})
        self.assertEqual(written['error_code'],'HOST_OWNED_FILE')
        patched = self.tools['apply_project_patch'].invoke({
            'expected_version':2,'path':'diagram.json','old_text':'mcu:1','new_text':'mcu:2'})
        self.assertEqual(patched['error_code'],'HOST_OWNED_FILE')
        self.assertEqual(Path(generated['artifacts']['json']).read_bytes(), original_report)
        self.assertEqual(self.p.get()['version'],2)

    def test_catalog_owned_simulation_attrs_are_hard_contract(self):
        from hardware_claw.validation.files import check
        state = state_for({'ring':'ws2812_ring_8'}, [
            ('mcu:4','ring:DIN'), ('mcu:5V','ring:VCC'), ('mcu:GND.1','ring:GND')])
        state['template'] = 'vscode'
        state['design'] |= {'goal':'attribute contract fixture', 'simulation_only':True,
                            'dependencies':[], 'assumptions':[]}
        diagram = json.loads(state['files']['diagram.json'])
        ring = next(part for part in diagram['parts'] if part['id']=='ring')
        for attrs in ({}, {'pixels':'16'}, {'pixels':'8','brightness':'40'}):
            with self.subTest(attrs=attrs):
                ring['attrs'] = attrs
                state['files']['diagram.json'] = json.dumps(diagram)
                self.assertIn('SIMULATION_ATTRS_MISMATCH',
                              {item['code'] for item in check(state)['issues']})
        ring['attrs'] = {'pixels':'8'}
        state['files']['diagram.json'] = json.dumps(diagram)
        self.assertNotIn('SIMULATION_ATTRS_MISMATCH',
                         {item['code'] for item in check(state)['issues']})

    def test_scaffold_uses_catalog_owned_wokwi_attributes(self):
        design = {'goal':'WS2812 attribute fixture', 'simulation_only':True,
                  'board_id':BOARD,
                  'components':[{'instance_id':'ring','hardware_id':'ws2812_ring_8'}],
                  'connections':[
                      {'a':'mcu:4','b':'ring:DIN'},
                      {'a':'mcu:5V','b':'ring:VCC'},
                      {'a':'mcu:GND.1','b':'ring:GND'}],
                  'dependencies':[], 'assumptions':[], 'pin_defines':{'RING_PIN':4}}
        self.tools['update_project_design'].invoke({'expected_version':0,'design':design})
        result = self.tools['scaffold_project'].invoke({'expected_version':1})
        self.assertEqual(result['execution_status'],'ok')
        diagram = json.loads(self.p.read_file('diagram.json')['content'])
        ring = next(part for part in diagram['parts'] if part['id']=='ring')
        self.assertEqual(ring['attrs'], {'pixels':'8'})

    def test_external_change_is_not_accepted_as_new_gpio_table(self):
        self.p.update_design(0, self.design)
        self.p.scaffold(1)
        (self.p.files/'diagram.json').write_text('{}',encoding='utf8')
        result = self.tools['get_project'].invoke({})
        self.assertEqual(result['error_code'],'EXTERNAL_CHANGE')

    def test_unregistered_dependency_version_is_not_silently_installed(self):
        self.design['dependencies'] = [{'name':'ESP32Servo','version':'99.99.99'}]
        self.p.update_design(0,self.design)
        result = self.tools['scaffold_project'].invoke({'expected_version':1})
        self.assertEqual(result['error_code'],'UNSUPPORTED_DEPENDENCY')
        self.assertEqual(self.p.get()['version'],1)


if __name__ == '__main__':
    unittest.main()
