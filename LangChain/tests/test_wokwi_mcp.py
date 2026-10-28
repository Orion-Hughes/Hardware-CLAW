import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from hardware_claw.contracts.simulation_mcp import InspectSimulationInput, MCPAction
from hardware_claw.adapters.wokwi_mcp import decode_result, validate_config, validate_controls, inspect, read_evidence
from hardware_claw.projects.service import ProjectError, atomic_json
from hardware_claw.runtime import execute_turn
from test_agent import ScriptedModel
from tests import test_vscode_delivery as fixtures


class MCPContractTests(unittest.TestCase):
    def test_paths_and_unbounded_inputs_rejected(self):
        bad = [
            {"operation": "wokwi_start_simulation", "arguments": {"projectPath": "D:/"}},
            {"operation": "wokwi_start_simulation", "arguments": {"sdcard": "../private"}},
            {"operation": "wokwi_export_vcd", "arguments": {"outputPath": "../outside"}},
            {"operation": "read_resource", "arguments": {"name": "../DS_Api.txt"}},
            {"operation": "wait", "arguments": {"milliseconds": -1}},
            {"operation": "wait", "arguments": {"milliseconds": True}},
            {"operation": "wokwi_set_control", "arguments": {"partId": "p", "control": "x", "value": float('nan')}},
            {"operation": "wokwi_read_pin", "arguments": {"partId": "p"}},
        ]
        for action in bad:
            with self.subTest(action=action), self.assertRaises(ValidationError):
                InspectSimulationInput.model_validate({"expected_version": 1, "actions": [action]})
        with self.assertRaises(ValidationError):
            InspectSimulationInput.model_validate({"expected_version": 1, "actions": [{"operation": "wait", "arguments": {"milliseconds":10000}}]*7})

    def test_official_errors_not_confused_with_serial_business_output(self):
        raw = {"content": [{"type": "text", "text": "Error: invalid part"}], "isError": False}
        self.assertEqual(decode_result(raw, "wokwi_read_pin")["status"], "tool_error")
        self.assertEqual(decode_result(raw, "wokwi_read_serial")["status"], "ok")
        raw["isError"] = True
        self.assertEqual(decode_result(raw, "wokwi_read_serial")["status"], "tool_error")

    def test_screenshot_prefix_is_not_an_image(self):
        raw = {"content": [{"type": "text", "text": "Screenshot taken (base64): " + "a"*100 + "..."}]}
        self.assertEqual(decode_result(raw, "wokwi_take_screenshot")["status"], "unsupported")

    def test_missing_voltage_is_partial_not_zero(self):
        raw = {"content":[{"type":"text", "text":"Pin 4 on mcu: false (undefinedV)"}]}
        result = decode_result(raw, "wokwi_read_pin")
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["pin_state"]["voltage"])
        self.assertFalse(result["pin_state"]["value"])

    def test_unknown_control_rejected_even_if_official_server_would_acknowledge(self):
        state = {"design":{"board_id":"esp32_s3_devkitc1_n32r16v", "components":[{"instance_id":"input", "hardware_id":"ps2_joystick"}]}}
        valid = MCPAction(operation="wokwi_set_control",arguments={"partId":"input","control":"x","value":1})
        validate_controls(state, [valid])
        for changes in ({"control":"invented"}, {"value":2}, {"partId":"missing"}):
            invalid = MCPAction(operation="wokwi_set_control",arguments=valid.arguments | changes)
            with self.assertRaises(ProjectError):
                validate_controls(state, [invalid])
        raw = {"content":[{"type":"text", "text":"Set x on input to 1"}]}
        self.assertFalse(decode_result(raw,"wokwi_set_control")["effect_verified"])

    def test_external_config_rejected(self):
        for config in ('[wokwi]\nversion=1\nfirmware="../private.bin"', '[wokwi]\nversion=1\nfirmware="firmware/firmware.bin"\nelf="firmware/firmware.elf"\n[[chip]]\nname="outside"'):
            with self.assertRaises(ProjectError):
                validate_config(config)


class MCPStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = fixtures.VSCodeTests()
        self.fixture.setUp()
        self.p = self.fixture.p
        self.p.check_files()
        self.fixture.fake_build()

    async def fake_session(self, work, actions, token):
        self.assertTrue((work/'firmware/firmware.bin').exists())
        self.assertNotIn('DS_Api.txt', [p.name for p in work.iterdir()])
        report = {"execution_status": "completed", "records": [], "full_project_acceptance": "not_evaluated"}
        atomic_json(work/'result.json', report)
        return report

    async def test_evidence_version_binding_and_no_acceptance_promotion(self):
        with patch('hardware_claw.adapters.wokwi_mcp.run_session', side_effect=self.fake_session), patch('hardware_claw.adapters.wokwi_mcp.read_token', return_value='TEST_ONLY'), patch('hardware_claw.adapters.wokwi_mcp.CLI', Path(__file__)):
            report = await inspect(self.p, 3, [{"operation": "wokwi_get_status"}])
        self.assertTrue((Path(report['evidence_directory'])/'manifest.json').exists())
        self.assertEqual(report['version'], 3)
        self.assertEqual(report['full_project_acceptance'], 'not_evaluated')
        self.assertEqual(self.p.get()['behavior'], 'not_run')
        self.assertFalse((self.p.meta/'simulation.json').exists())
        with self.assertRaises(ProjectError):
            await inspect(self.p, 2, [{"operation": "wokwi_get_status"}])

    async def test_change_during_session_does_not_publish_evidence(self):
        async def changed(work, actions, token):
            result = await self.fake_session(work, actions, token)
            self.p.write_files(3, {'README.md':'new revision'})
            return result
        with patch('hardware_claw.adapters.wokwi_mcp.run_session', side_effect=changed), patch('hardware_claw.adapters.wokwi_mcp.read_token', return_value='TEST_ONLY'), patch('hardware_claw.adapters.wokwi_mcp.CLI', Path(__file__)):
            with self.assertRaises(ProjectError):
                await inspect(self.p, 3, [{"operation": "wokwi_get_status"}])
        self.assertFalse((self.p.meta/'mcp').exists())

    async def test_paginated_evidence_and_tamper_detection(self):
        with patch('hardware_claw.adapters.wokwi_mcp.run_session', side_effect=self.fake_session), patch('hardware_claw.adapters.wokwi_mcp.read_token', return_value='TEST_ONLY'), patch('hardware_claw.adapters.wokwi_mcp.CLI', Path(__file__)):
            report = await inspect(self.p, 3, [{"operation":"wokwi_get_status"}])
        chunks, offset = [], 0
        while offset is not None:
            page = read_evidence(self.p,3,report['attempt'],'result.json',offset,17)
            chunks.append(page['content'])
            offset = page['next_offset']
        path = Path(report['evidence_directory'])/'result.json'
        self.assertEqual(''.join(chunks),path.read_bytes().decode('utf-8'))
        path.write_text('forged',encoding='utf-8')
        with self.assertRaises(ProjectError) as caught:
            read_evidence(self.p,3,report['attempt'],'result.json')
        self.assertEqual(caught.exception.code,'EVIDENCE_CHANGED')

    async def test_full_agent_routes_new_tool(self):
        class Model(ScriptedModel):
            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                self._count += 1
                if self._count == 1:
                    message = AIMessage(content='',tool_calls=[{'name':'inspect_simulation','id':'mcp-1','type':'tool_call','args':{'expected_version':3,'actions':[{'operation':'wokwi_get_status'}]}}])
                elif self._count == 2:
                    evidence = json.loads(next(m.content for m in reversed(messages) if isinstance(m,ToolMessage)))['data']
                    message = AIMessage(content='',tool_calls=[{'name':'read_simulation_evidence','id':'evidence-1','type':'tool_call','args':{'expected_version':3,'attempt':evidence['attempt'],'filename':'result.json','limit':1000}}])
                else:
                    assert any(isinstance(m,ToolMessage) and 'not_evaluated' in m.content for m in messages)
                    message = AIMessage(content='Observed; behavior not evaluated.')
                return ChatResult(generations=[ChatGeneration(message=message)])
        events=[]
        async def emit(kind,data): events.append((kind,data))
        with patch('hardware_claw.adapters.wokwi_mcp.run_session', side_effect=self.fake_session), patch('hardware_claw.adapters.wokwi_mcp.read_token', return_value='TEST_ONLY'), patch('hardware_claw.adapters.wokwi_mcp.CLI', Path(__file__)):
            status=await execute_turn(Model(),'inspect current simulation',[],emit,project=self.p)
        self.assertEqual(status,'completed')
        self.assertEqual(events[-1][1]['tool_requests'],2)
