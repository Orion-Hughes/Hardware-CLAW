"""Malformed-report fixtures exercise the real graph; no production hardware answers."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import Field

from hardware_claw import limits
from hardware_claw.coordinator import Coordinator, TaskStore
from hardware_claw.coordinator.store import ROOT
from hardware_claw.stages.selection import attach_selection
from test_selection_agent import FixtureModel

BAD_JSON = '{"status":"completed","summary":未加引号}'


class MalformedModel(FixtureModel):
    mode: str = 'json_once'
    seen: list = Field(default_factory=list)
    bound_names: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        self.bound_names.append([t.get('function', {}).get('name') if isinstance(t, dict) else t.name for t in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        index = len(self.seen)
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        msg = result.generations[0].message
        if index == 1:
            return result  # Actual local read_hardware, no API.
        malformed = (index == 2 and self.mode not in ('semantic_then_json', 'legacy_stage_hint')) or self.mode == 'json_twice' or (
            index == 3 and self.mode == 'semantic_then_json')
        if index == 2 and self.mode == 'no_report':
            msg = AIMessage(content='no report', usage_metadata=msg.usage_metadata)
        elif malformed:
            valid_calls = []
            if self.mode == 'mixed':
                valid_calls = [{'name':'read_hardware','args':{'hardware_ids':['dht22_red_module']},'id':'pending-read'}]
            elif self.mode == 'ambiguous':
                valid_calls = msg.tool_calls
            msg = AIMessage(content='', tool_calls=valid_calls,
                invalid_tool_calls=[{'name':'read_hardware' if self.mode == 'unrelated_invalid' else 'SelectionReport',
                    'args':BAD_JSON, 'id':f'bad-{index}', 'error':'invalid JSON'}], usage_metadata=msg.usage_metadata)
        elif self.mode == 'legacy_stage_hint' and index == 2:
            msg.tool_calls[0]['args']['next_stage'] = 'null'
        elif self.mode in ('json_then_semantic', 'semantic_then_json'):
            msg.tool_calls[0]['args']['source_refs'] = ['upstream/invented.md']
        elif self.mode == 'json_then_schema':
            msg.tool_calls[0]['args']['assumptions'] = [['nested']]
        elif self.mode == 'json_then_queries':
            msg.tool_calls = [{'name':'read_hardware','args':{'hardware_ids':['dht22_red_module']},'id':'unexpected-read'}]
        return ChatResult(generations=[ChatGeneration(message=msg)])


class JsonRepairTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        root = ROOT/'temp/selection-json-tests'
        root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        store = TaskStore(Path(self.tmp.name))
        self.c = Coordinator(store.create(), store=store)
        self.c.begin_turn('fixture selection')

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def run_child(self, mode='json_once'):
        model = MalformedModel(mode=mode)
        attach_selection(self.c, model)
        result = await self.c.run_stage('selection','fixture',self.c.state()['version'])
        detail = self.c.store.record(self.c.task_id,result['result']['detail_ref'])
        return model, result, detail

    async def test_exact_json_and_location_return_to_same_context_without_reread(self):
        model, result, detail = await self.run_child()
        self.assertEqual(result['status'],'completed')
        self.assertEqual(detail['metrics']['model_responses'],3)
        self.assertEqual(detail['metrics']['tokens_reported'],36)
        self.assertTrue(detail['metrics']['usage_complete'])
        self.assertEqual(detail['metrics']['tool_calls'],1)
        feedback = [m for m in model.seen[-1] if isinstance(m,ToolMessage) and m.name=='SelectionReport']
        self.assertEqual(len(feedback),1)
        payload = json.loads(feedback[0].content)
        self.assertEqual(payload['raw_arguments'],BAD_JSON)
        self.assertGreater(payload['parser_error']['column'],1)
        self.assertEqual(feedback[0].tool_call_id,'bad-2')
        self.assertTrue(any(isinstance(m, ToolMessage) and m.name=='read_hardware' for m in model.seen[-1]))
        self.assertEqual(model.bound_names[-1],['SelectionReport'])
        original = [e for e in detail['events'] if e['kind']=='model' and e['invalid_tool_calls']]
        self.assertEqual(original[0]['invalid_tool_calls'][0]['args'],BAD_JSON)

    async def test_repeated_json_error_stops_and_counts_billed_responses(self):
        model, result, detail = await self.run_child('json_twice')
        self.assertEqual(result['result']['blockers'],['INVALID_REPORT_JSON'])
        self.assertEqual(len(model.seen),3)
        self.assertEqual(detail['metrics']['tokens_reported'],36)
        self.assertFalse(self.c.state()['latest'])
        self.assertIsNone(self.c.state()['active_run'])

    async def test_json_then_semantic_failure_cannot_bypass_evidence_or_gain_retry(self):
        model, result, detail = await self.run_child('json_then_semantic')
        self.assertEqual(result['result']['blockers'],['UNREAD_SOURCE'])
        self.assertEqual(len(model.seen),3)
        self.assertEqual(detail['metrics']['tokens_reported'],36)

    async def test_semantic_then_json_failure_uses_same_allowance(self):
        model, result, detail = await self.run_child('semantic_then_json')
        self.assertEqual(result['result']['blockers'],['INVALID_REPORT_JSON'])
        self.assertEqual(len(model.seen),3)
        self.assertEqual(detail['metrics']['tokens_reported'],36)

    async def test_json_then_schema_failure_is_not_accepted(self):
        _, result, detail = await self.run_child('json_then_schema')
        self.assertEqual(result['result']['blockers'],['INVALID_HANDOFF'])
        self.assertEqual(detail['metrics']['tokens_reported'],36)

    async def test_extra_routing_field_gets_exact_removal_feedback(self):
        model, result, detail = await self.run_child('legacy_stage_hint')
        self.assertEqual(result['status'], 'completed')
        self.assertNotIn('next_stage', result['result'])
        self.assertEqual(model.bound_names[-1], ['SelectionReport'])
        self.assertEqual(detail['metrics']['tool_calls'], 1)
        feedback = next(m for m in model.seen[-1] if isinstance(m, ToolMessage) and m.name == 'SelectionReport')
        issue = json.loads(feedback.content)['issues'][0]
        self.assertEqual((issue['field'], issue['type'], issue['received'], issue['fix']),
                         ('next_stage', 'extra_forbidden', '"null"', '删除该字段。'))

    async def test_repair_still_obeys_token_budget(self):
        with patch.object(limits,'SELECTION_TOTAL_TOKENS',24):
            model, result, detail = await self.run_child()
        self.assertEqual(result['result']['blockers'],['SELECTION_TOKEN_BUDGET'])
        self.assertEqual(len(model.seen),2)
        self.assertEqual(detail['metrics']['tokens_reported'],24)

    async def test_repair_still_obeys_model_call_limit(self):
        with patch.object(limits,'SELECTION_MODEL_CALLS',2):
            model, result, detail = await self.run_child()
        self.assertEqual(result['result']['blockers'],['ModelCallLimitExceededError'])
        self.assertEqual(len(model.seen),2)

    async def test_no_report_and_unrelated_malformed_tool_not_fabricated_as_report(self):
        for mode in ('no_report','unrelated_invalid'):
            model, result, detail = await self.run_child(mode)
            self.assertEqual(result['result']['blockers'],['MISSING_REPORT'])
            self.assertEqual(len(model.seen),2)

    async def test_mixed_pending_calls_finish_before_report_resubmission(self):
        model, result, detail = await self.run_child('mixed')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(detail['metrics']['tool_calls'],2)
        self.assertTrue(any(isinstance(m,ToolMessage) and m.tool_call_id=='pending-read' for m in model.seen[-1]))

    async def test_valid_and_malformed_reports_in_same_response_are_rejected(self):
        _, result, detail = await self.run_child('ambiguous')
        self.assertEqual(result['result']['blockers'],['AMBIGUOUS_REPORT'])
        self.assertFalse(self.c.state()['latest'])

    async def test_no_new_business_calls_during_syntax_repair(self):
        _, result, detail = await self.run_child('json_then_queries')
        self.assertEqual(result['result']['blockers'],['REPORT_REPAIR_SCOPE'])
        self.assertEqual(detail['metrics']['tool_calls'],1)
        self.assertEqual(detail['metrics']['tokens_reported'],36)
