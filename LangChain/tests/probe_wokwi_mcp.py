"""Opt-in live protocol probe. No LLM calls. Prepared fixture is compiled under temp.

Run from repository root:
LangChain/.venv/Scripts/python.exe -X utf8 -B LangChain/tests/probe_wokwi_mcp.py --prepared-project temp/wokwi-mcp-research/transport-fixture
"""
import argparse
import asyncio
import json
import shutil
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hardware_claw.adapters.wokwi_mcp import run_session
from hardware_claw.adapters.png_evidence import png_info
from hardware_claw.adapters.simulator import read_token
from hardware_claw.contracts.simulation_mcp import InspectSimulationInput
from hardware_claw.projects.service import ROOT, atomic_json


def action(operation, **arguments):
    return {"operation": operation if operation in {"wait", "read_resource"} else "wokwi_"+operation, "arguments": arguments}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared-project', type=Path, required=True)
    args = parser.parse_args()
    work = ROOT/'temp/mcp-probes'/uuid.uuid4().hex
    work.mkdir(parents=True)
    for name in ('diagram.json','wokwi.toml','firmware/firmware.bin','firmware/firmware.elf'):
        target = work/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.prepared_project/name,target)
    actions = [
        action('read_resource',name='diagram.json'), action('read_resource',name='wokwi.toml'),
        action('wait',milliseconds=5000), action('get_status'), action('read_serial'),
        action('write_serial',text='MCP_ECHO_CHECK\n'), action('wait',milliseconds=3000), action('read_serial',clear=True), action('read_serial'),
        action('set_control',partId='input',control='x',value=-1), action('wait',milliseconds=2000), action('read_pin',partId='input',pin='HORZ'), action('read_serial'),
        action('set_control',partId='input',control='x',value=1), action('wait',milliseconds=2000), action('read_pin',partId='input',pin='HORZ'), action('read_serial'),
        action('set_control',partId='input',control='pressed',value=1), action('read_pin',partId='mcu',pin='4'),
        action('take_screenshot',partId='screen'),
        action('stop_simulation'), action('get_status'), action('wait',milliseconds=1000), action('get_status'), action('export_vcd'),
        action('resume_simulation'), action('get_status'), action('restart_simulation'), action('get_status'),
        action('start_simulation'), action('get_status'),
    ]
    request = InspectSimulationInput.model_validate({'expected_version':0,'actions':actions})
    result = await run_session(work, request.actions, read_token())
    records = result['records']
    serial = [r for r in records if r['operation']=='wokwi_read_serial']
    statuses = [r.get('simulation_status',{}) for r in records if r['operation']=='wokwi_get_status']
    checks = {
        'serial_fixture_output': any('MCP_TRANSPORT_FIXTURE' in r.get('text','') for r in serial),
        'serial_write_echo': any('MCP_ECHO_CHECK' in r.get('text','') for r in serial),
        'serial_clear': len(serial)>2 and 'MCP_ECHO_CHECK' not in serial[2].get('text',''),
        'control_adc_low': any('adc=0 ' in r.get('text','') for r in serial[3:4]),
        'control_adc_high': any('adc=4095 ' in r.get('text','') for r in serial[4:5]),
        'pause_time_stable': len(statuses)>=3 and statuses[1].get('running') is False and statuses[1].get('nanos')==statuses[2].get('nanos'),
        'resume_running': len(statuses)>=4 and statuses[3].get('running') is True,
        'restart_resets_clock': len(statuses)>=5 and statuses[4].get('nanos',float('inf')) < statuses[3].get('nanos',0),
        'vcd_has_timestamps': any('$enddefinitions' in p.read_text() and '\n#' in p.read_text() for p in work.glob('waveform-*.vcd')),
        'resources_match_snapshot': sum(r['status']=='ok' for r in records if r['operation']=='read_resource')==2,
    }
    if result.get('backend', {}).get('kind') == 'upstream_with_local_generic_patch':
        screenshots = [r for r in records if r['operation']=='wokwi_take_screenshot']
        checks['complete_png'] = bool(screenshots) and all(r['status']=='ok' and png_info((work/r['artifact']).read_bytes())['complete'] for r in screenshots)
        pins = [r for r in records if r['operation']=='wokwi_read_pin']
        checks['explicit_digital_only_scope'] = bool(pins) and all(r.get('scope')=='digital_logic_only' and r.get('pin_state',{}).get('voltage') is None for r in pins)
    atomic_json(work/'probe-checks.json',checks)
    print(json.dumps({'evidence':str(work),'execution_status':result['execution_status'],'checks':checks,
                      'operations':[{'operation':r['operation'],'status':r['status'],'text':r.get('text','')[:250]} for r in records]},ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__': asyncio.run(main())
