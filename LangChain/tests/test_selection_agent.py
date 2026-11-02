"""Offline mechanism tests, never firmware templates or device acceptance."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatResult, ChatGeneration

from hardware_claw import limits
from hardware_claw.coordinator import Coordinator, TaskStore, WorkflowError
from hardware_claw.coordinator.store import ROOT
from hardware_claw.runtime import execute_turn
from hardware_claw.stages.selection import SelectionExecutor, SelectionTrace, SelectionReport, attach_selection
from hardware_claw.tools.hardware_catalog import read_hardware


class FixtureModel(BaseChatModel):
    mode: str = 'normal'
    @property
    def _llm_type(self): return 'selection-mechanism-fixture'
    def bind_tools(self, tools, **kwargs): return self
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        child = '选型子Agent' in messages[0].content
        last = messages[-1]
        if child:
            if not isinstance(last, ToolMessage) and self.mode != 'skip_read':
                name, args = 'read_hardware', {'hardware_ids': ['dht22_red_module'], 'view': 'selection'}
            else:
                name, args = 'SelectionReport', {'status': 'completed', 'summary': 'fixture selection',
                    'requirements': ['measure temperature'], 'hardware_ids': ['dht22_red_module'],
                    'source_refs': ['cards/dht22_red_module.json'] if self.mode != 'skip_read' else []}
                context = json.loads(next(m.content for m in messages if m.type == 'human'))
                if context.get('accepted_selection', {}).get('previous', {}).get('hardware_ids'):
                    args['compatibility'] = {'verdict': 'compatible', 'hardware_ids': args['hardware_ids'],
                        **{k: 'fixture review' for k in ('requirements','interfaces','resources','electrical','platform')}}
                if self.mode == 'invent_source': args['source_refs'] = ['upstream/invented.md']
                if self.mode == 'repair' and not (isinstance(last, ToolMessage) and last.name == 'SelectionReport'):
                    args['source_refs'] = ['upstream/invented.md']
        elif not isinstance(last, ToolMessage):
            name, args = 'get_task_state', {}
        elif last.name == 'get_task_state':
            data = json.loads(last.content)['data']
            name, args = 'run_stage', {'stage': 'selection', 'objective': 'fixture task', 'expected_task_version': data['version']}
        else:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='选型已完成，未生成或验证。',
                usage_metadata={'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12}))])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='',
            tool_calls=[{'id': str(len(messages)), 'name': name, 'args': args, 'type': 'tool_call'}],
            usage_metadata={'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12}))])


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        root = ROOT / 'temp/selection-tests'
        root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        store = TaskStore(Path(self.tmp.name))
        self.c = Coordinator(store.create(), store=store)
        self.c.begin_turn('fixture user request')

    async def asyncTearDown(self): self.tmp.cleanup()

    async def child(self, model=None):
        attach_selection(self.c, model or FixtureModel())
        return await self.c.run_stage('selection', 'fixture task', self.c.state()['version'])

    def test_selection_view_preserves_scope_and_does_not_load_source_text(self):
        result = read_hardware.invoke({'hardware_ids':['dht22_red_module', 'st7789_240x240_simulation'], 'view':'selection'})
        d = result['data']
        self.assertEqual(d['mode'], 'selection')
        self.assertEqual(len(d['hardware']), 2)
        self.assertEqual(d['hardware'][0]['availability']['simulation_test'], 'not_run')
        self.assertEqual(d['hardware'][1]['summary']['record_role'], 'simulation_variant')
        for item in d['hardware']:
            self.assertTrue(item['provenance']['record']['sha256'])
            for group in item['documents'].values():
                self.assertTrue(all('content' not in entry for entry in group))
        self.assertLess(len(json.dumps(d)), 35000)

    def test_default_usage_view_and_selection_errors(self):
        self.assertEqual(read_hardware.invoke({'hardware_ids':['dht22_red_module']})['data']['mode'], 'essentials')
        result = read_hardware.invoke({'hardware_ids':['unknown-fixture'], 'view':'selection'})
        self.assertFalse(result['data']['complete'])
        self.assertEqual(result['data']['errors'][0]['error_code'], 'NOT_FOUND')
        bad = read_hardware.invoke({'hardware_ids':['dht22_red_module'], 'view':'selection', 'references':['x']})
        self.assertEqual(json.loads(bad)['error_code'], 'INVALID_ARGUMENT')

    def test_child_has_only_read_tools(self):
        self.assertEqual([t.name for t in SelectionTrace(self.c).make_tools()], ['search_hardware','read_hardware'])

    async def test_selection_rejects_whole_programming_packet(self):
        trace = SelectionTrace(self.c)
        tool = trace.make_tools()[1]
        blocked = await tool.ainvoke({'hardware_ids':['dht22_red_module'], 'view':'usage'})
        self.assertEqual(blocked['error_code'], 'STAGE_SCOPE')
        self.assertFalse(trace.observed)
        default = await tool.ainvoke({'hardware_ids':['dht22_red_module']})
        self.assertEqual(default['data']['mode'], 'selection')
        self.assertIn('platforms/esp32_s3_simulation.json', trace.sources)
        self.assertIn('catalog.json', trace.sources)

    async def test_standalone_graph_handoff_usage_and_persistence(self):
        result = await self.child()
        self.assertEqual(result['status'], 'completed')
        detail = self.c.store.record(self.c.task_id, result['result']['detail_ref'])
        self.assertEqual(detail['metrics']['model_responses'], 2)
        self.assertEqual(detail['metrics']['tokens_reported'], 24)
        self.assertEqual(self.c.state()['usage']['total_tokens'], 24)
        self.assertEqual(self.c.state()['usage_by_role']['selection']['total_tokens'], 24)
        self.assertNotIn('messages', detail['context'])
        self.assertIsNone(self.c.state()['project_id'])
        self.assertTrue(detail['events'])
        with self.assertRaises(WorkflowError) as caught:
            await self.c.run_stage('selection', 'fixture', self.c.state()['version'], [detail['run_id']])
        self.assertEqual(caught.exception.code, 'INVALID_REFERENCE')

    async def test_unread_hardware_and_invented_source_not_completed(self):
        result = await self.child(FixtureModel(mode='skip_read'))
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('UNREAD_HARDWARE', result['result']['blockers'])
        self.c.executors.clear()
        result = await self.child(FixtureModel(mode='invent_source'))
        self.assertIn('UNREAD_SOURCE', result['result']['blockers'])
        self.assertFalse(self.c.state()['latest'])
        detail = self.c.store.record(self.c.task_id, result['result']['detail_ref'])
        self.assertEqual(detail['metrics']['model_responses'], 3)
        self.assertEqual(detail['metrics']['tokens_reported'], 36)
        self.assertTrue(detail['metrics']['usage_complete'])

    async def test_report_validation_can_correct_once_without_reloading_hardware(self):
        result = await self.child(FixtureModel(mode='repair'))
        self.assertEqual(result['status'], 'completed')
        detail = self.c.store.record(self.c.task_id, result['result']['detail_ref'])
        self.assertEqual(detail['metrics']['model_responses'], 3)
        self.assertEqual(detail['metrics']['tool_calls'], 1)
        feedback = [e for e in detail['events'] if e['kind'] == 'submission_feedback']
        self.assertTrue(any('upstream/invented.md' in e['content'] for e in feedback))

    async def test_child_budget_shares_parent_task_ledger(self):
        self.c.record_usage({'input_tokens': 1,'output_tokens':1,'total_tokens':2})
        with patch.object(limits, 'COORDINATOR_TOTAL_TOKENS', 14):
            result = await self.child()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('TOKEN_BUDGET', result['result']['blockers'])
        self.assertEqual(self.c.state()['usage']['total_tokens'], 14)
        self.assertIsNone(self.c.state()['active_run'])

    async def test_per_stage_token_budget_is_enforced(self):
        with patch.object(limits, 'SELECTION_TOTAL_TOKENS', 12):
            result = await self.child()
        self.assertIn('SELECTION_TOKEN_BUDGET', result['result']['blockers'])

    async def test_parent_routes_child_and_total_usage_is_not_double_counted(self):
        events = []
        async def emit(kind, data): events.append((kind, data))
        self.c.builtin_stages = True
        status = await execute_turn(FixtureModel(), 'fixture selection', [], emit, coordinator=self.c)
        self.assertEqual(status, 'completed')
        summary = events[-1][1]
        self.assertEqual(summary['main_model_responses'], 3)
        self.assertEqual(summary['model_responses'], 5)
        self.assertEqual(summary['tokens_reported'], 60)
        self.assertEqual(summary['coordinator']['usage']['total_tokens'], 60)
        self.assertEqual(len(summary['child_runs']), 1)
        # Child tool results are absent from the parent tool payloads.
        self.assertEqual(set(summary['tool_payload_characters']), {'get_task_state','run_stage'})
        # Reusing a coordinator refreshes the current turn's observer, not old events.
        events.clear()
        await execute_turn(FixtureModel(), 'another request', [], emit, coordinator=self.c)
        self.assertEqual(events[-1][1]['tokens_reported'], 60)
        self.assertEqual(events[-1][1]['coordinator']['usage']['total_tokens'], 120)

    async def test_blocked_hardware_cannot_be_completed(self):
        trace = SelectionTrace(self.c)
        tool = next(t for t in trace.make_tools() if t.name == 'read_hardware')
        await tool.ainvoke({'hardware_ids':['usb_camera'], 'view':'selection'})
        with self.assertRaises(WorkflowError):
            trace.validate(SelectionReport(status='completed',summary='fixture',requirements=['camera'],hardware_ids=['usb_camera']))

    async def test_child_cancel_records_usage_and_releases_task(self):
        model = FixtureModel()
        async def hang(*args, **kwargs):
            await asyncio.sleep(30)
        with patch.object(type(model), '_agenerate', hang):
            attach_selection(self.c, model)
            task = asyncio.create_task(self.c.run_stage('selection','fixture',self.c.state()['version']))
            await asyncio.sleep(0.1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertIsNone(self.c.state()['active_run'])
        self.assertEqual(self.c.state()['latest_outcome'], 'cancelled')
