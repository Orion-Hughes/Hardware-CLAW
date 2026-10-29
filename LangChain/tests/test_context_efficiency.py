import copy
import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from hardware_claw.catalog import KnowledgeCatalog, CatalogError
from hardware_claw.catalog.driver_api import get_driver_api, read_source
from hardware_claw.tools.hardware_catalog import get_hardware_info
from hardware_claw.tools.driver_api import get_driver_api as api_tool
from hardware_claw.message_view import build_view, complete_rounds


def tool_round(n, name, data, args=None, status='ok'):
    call = {'id': str(n), 'name': name, 'args': args or {}, 'type': 'tool_call'}
    result = {'execution_status': status, 'error_code': 'FIXTURE' if status == 'error' else None, 'data': data}
    return [AIMessage(content='', tool_calls=[call]),
            ToolMessage(content=json.dumps(result), tool_call_id=str(n))]


class CompactCatalogTests(unittest.TestCase):
    def test_bad_section_reports_real_available_fields_without_another_read(self):
        for ident in ('esp32_s3_devkitc1_n32r16v','mpu6050'):
            known=get_hardware_info.invoke({'hardware_id':ident})['data']['available_sections']
            error=get_hardware_info.invoke({'hardware_id':ident,'sections':['invented_profile_field']})
            self.assertEqual(error['error_code'],'INVALID_ARGUMENT')
            for name in known:
                self.assertIn(name,error['summary'])
            self.assertNotIn('invented_profile_field',error['summary'])

    def test_hardware_preserves_constraints_and_full_escape(self):
        for ident in ('mpu6050', 'sg90_180', 'usb_camera'):
            small = get_hardware_info.invoke({'hardware_id': ident})['data']
            full = get_hardware_info.invoke({'hardware_id': ident, 'detail': 'full'})['data']
            self.assertEqual(small['summary'], full['summary'])
            for key in ('simulation', 'electrical_profile', 'generation_profile', 'missing_information', 'notes'):
                self.assertEqual(small['profile'].get(key), full['profile'].get(key))
            self.assertEqual(small['provenance'], full['provenance'])
            self.assertLess(len(json.dumps(small)), len(json.dumps(full)))

    def test_api_compact_pagination_and_noise_filter(self):
        c = KnowledgeCatalog()
        full = get_driver_api(c, 'mpu6050')
        self.assertTrue(all('.github/' not in ref and 'code-of-conduct' not in ref for ref in full['references']))
        refs, offset = [], 0
        while offset is not None:
            data = get_driver_api(c, 'mpu6050', offset=offset, detail='compact')
            refs.extend(data['references'])
            offset = data['next_offset']
        self.assertEqual(set(refs), set(full['references']))
        self.assertEqual(len(refs), len(set(refs)))
        result = api_tool.invoke({'hardware_id': 'mpu6050'})
        self.assertNotIn('source_refs', result['data']['driver_profile'])

    def test_search_returns_exact_original_spans_and_source_identity(self):
        c = KnowledgeCatalog()
        for ident, query in [('mpu6050', 'getEvent'), ('sg90_180', 'attach('), ('potentiometer', 'analogRead')]:
            result = get_driver_api(c, ident, query=query, limit=900)
            self.assertTrue(result['matches'])
            self.assertLessEqual(sum(len(h['content']) for h in result['matches']), 900)
            for hit in result['matches']:
                original, sha = read_source(c, hit['ref'])
                self.assertEqual(hit['sha256'], sha)
                self.assertEqual(hit['content'], original[hit['offset']:hit['end_offset']])
                self.assertEqual(hit['start_line'], original[:hit['offset']].count('\n')+1)
        self.assertEqual(get_driver_api(c, 'sg90_180', query='NOT_A_REAL_SYMBOL_987')['matches'], [])
        with self.assertRaises(CatalogError):
            get_driver_api(c, 'sg90_180', reference='../DS_Api.txt', query='attach')


class MessageViewTests(unittest.TestCase):
    def test_duplicate_reads_do_not_evict_distinct_api(self):
        first={'reference':{'ref':'a.h','sha256':'a','offset':0,'content':'API A'*500}}
        second={'reference':{'ref':'b.h','sha256':'b','offset':0,'content':'API B'*500}}
        messages=tool_round(0,'get_driver_api',first)+tool_round(1,'get_driver_api',second)+tool_round(2,'get_driver_api',second)
        for n in range(3,7):
            messages+=tool_round(n,'get_project',{'version':n})
        view,_=build_view(messages)
        self.assertEqual(json.loads(view[1].content)['data'],first)
        self.assertTrue(json.loads(view[3].content)['data']['context_view']['body_omitted'])
        self.assertEqual(json.loads(view[5].content)['data'],second)

    def test_short_results_never_grow_into_receipts(self):
        messages=[]
        for n in range(8):
            messages+=tool_round(n,'get_project',{'version':n,'files':[]})
        view,stats=build_view(messages)
        for before,after in zip(messages,view):
            if isinstance(before,ToolMessage):
                self.assertEqual(json.loads(before.content),json.loads(after.content))
        self.assertLessEqual(stats['model_message_chars'],stats['original_message_chars'])

    def test_latest_skill_body_replaces_changed_source(self):
        messages=tool_round(0,'load_skill',{'skill_id':'generic','sha256':'old','content':'OLD '*1000})
        messages+=tool_round(1,'load_skill',{'skill_id':'generic','sha256':'new','content':'NEW '*1000})
        for n in range(2,6):
            messages+=tool_round(n,'get_project',{'version':n})
        view,_=build_view(messages)
        self.assertTrue(json.loads(view[1].content)['data']['context_view']['body_omitted'])
        self.assertEqual(json.loads(view[3].content),json.loads(messages[3].content))

    def test_pairs_recent_rounds_and_original_evidence_preserved(self):
        messages = [HumanMessage(content='Constraint that must survive')]
        for n in range(7):
            messages += tool_round(n, 'read_project_file', {'path': 'src/main.cpp', 'content': 'x'*12000, 'version': n}, {'path': 'src/main.cpp'})
        original = copy.deepcopy(messages)
        view, stats = build_view(messages)
        self.assertEqual(messages, original)
        self.assertEqual(complete_rounds(view), complete_rounds(messages))
        self.assertEqual(view[0].content, messages[0].content)
        for a,b in zip(messages[-6:], view[-6:]):
            if isinstance(a, ToolMessage):
                self.assertEqual(json.loads(a.content), json.loads(b.content))
        self.assertLess(stats['model_message_chars'], stats['original_message_chars'] * .6)
        old = json.loads(view[2].content)['data']
        self.assertEqual(old['version'], 0)
        self.assertTrue(old['context_view']['historical'])
        self.assertEqual(old['context_view']['read_again']['tool'], 'read_project_file')

    def test_errors_skills_and_current_api_working_set_survive(self):
        messages = []
        messages += tool_round(0, 'load_skill', {'skill_id':'generic', 'sha256':'s', 'content':'critical workflow'})
        messages += tool_round(1, 'get_driver_api', {'reference': {'ref':'a.h','content':'first API'}})
        messages += tool_round(2, 'get_driver_api', {'reference': {'ref':'b.h','content':'second API'}})
        messages += tool_round(3, 'compile_project', {'verdict':'fail','scope':'compile','issues':['actual failure']}, status='error')
        for n in range(4,8):
            messages += tool_round(n, 'get_project', {'version':n})
        view,_ = build_view(messages)
        for index in (1,3,5,7):
            self.assertEqual(json.loads(view[index].content), json.loads(messages[index].content))

    def test_old_failed_verdict_not_changed_to_pass_and_write_not_reexecuted(self):
        messages = tool_round(0, 'compile_project', {'version':3,'verdict':'fail','scope':'compile','log_tail':'X'*6000,'issues':['error']})
        messages += tool_round(1, 'write_project_files', {'version':4}, {'expected_version':3,'files':{'src/main.cpp':'Y'*12000}})
        for n in range(2,6):
            messages += tool_round(n, 'get_project', {'version':4})
        view,_ = build_view(messages)
        result=json.loads(view[1].content)['data']
        self.assertEqual(result['verdict'], 'fail')
        self.assertEqual(result['version'],3)
        self.assertEqual(result['issues'],['error'])
        self.assertEqual(view[2].tool_calls[0]['id'], messages[2].tool_calls[0]['id'])
        self.assertIn('省略', view[2].tool_calls[0]['args']['files'])
        self.assertIsInstance(messages[2].tool_calls[0]['args']['files'], dict)

    def test_incomplete_parallel_group_never_projected(self):
        messages=tool_round(0,'write_project_files',{}, {'files':{'x':'x'*10000}})
        messages[0].tool_calls.append({'id':'missing','name':'get_project','args':{},'type':'tool_call'})
        for n in range(1,6):
            messages += tool_round(n,'get_project',{})
        view,_=build_view(messages)
        self.assertEqual(view[0].tool_calls,messages[0].tool_calls)


class ViewRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_runtime_records_view_metrics_and_raw_results(self):
        from test_agent import ScriptedModel
        from hardware_claw.runtime import execute_turn
        events=[]
        async def emit(kind, data):
            events.append((kind,data))
        self.assertEqual(await execute_turn(ScriptedModel(), 'offline fixture', [], emit), 'completed')
        summary=events[-1][1]
        self.assertTrue(all(m['context_view'] for m in summary['response_metrics']))
        result=next(data for kind,data in events if kind=='tool_result')
        self.assertIn('profile',json.loads(result['content'])['data'])
