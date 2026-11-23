import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from hardware_claw import limits
from hardware_claw.coordinator import Coordinator, TaskStore
from hardware_claw.coordinator.store import ROOT
from hardware_claw.runtime import execute_turn


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        base = ROOT / 'temp' / 'runtime-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        store = TaskStore(Path(self.tmp.name))
        self.coordinator = Coordinator(store.create(), store=store)
        self.events = []

    async def emit(self, kind, data):
        self.events.append((kind, data))

    async def run_graph(self, graph, history, **kwargs):
        with patch('hardware_claw.coordinator.agent.build_coordinator', return_value=graph):
            return await execute_turn(None, 'test request', history, self.emit, coordinator=self.coordinator, **kwargs)

    async def test_history_bounded_and_summary_persisted(self):
        class Graph:
            async def astream(self, inputs, **kwargs):
                assert len(inputs['messages']) == 2 * limits.HISTORY_TURNS + 1
                yield {'model': {'messages': [AIMessage(content='answer')]}}
        history = [m for _ in range(limits.HISTORY_TURNS + 2)
                   for m in (HumanMessage(content='old question'), AIMessage(content='old answer'))]
        self.assertEqual(await self.run_graph(Graph(), history), 'completed')
        self.assertEqual(len(history), 2 * limits.HISTORY_TURNS)
        self.assertEqual(history[-2].content, 'test request')
        summary = self.events[-1][1]
        saved = self.coordinator.store.record(self.coordinator.task_id, summary['run_id'])
        self.assertEqual(saved['kind'], 'main_turn')
        self.assertIsNone(summary['tokens_reported'])

    async def test_timeout_and_cancel(self):
        class SlowGraph:
            async def astream(self, *args, **kwargs):
                await asyncio.sleep(60)
                yield {}
        history = []
        self.assertEqual(await self.run_graph(SlowGraph(), history, timeout=0.01), 'error')
        self.assertEqual(history, [])
        self.assertIn('运行时限', self.events[-2][1]['text'])
        task = asyncio.create_task(self.run_graph(SlowGraph(), history))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.events[-1][1]['status'], 'cancelled')

    async def test_malformed_tool_arguments_are_not_execution_or_completion(self):
        class InvalidGraph:
            async def astream(self, *args, **kwargs):
                yield {'model': {'messages': [AIMessage(content='准备委派',
                    response_metadata={'finish_reason': 'tool_calls'},
                    usage_metadata={'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150},
                    invalid_tool_calls=[{'name': 'run_stage', 'args': '{', 'id': 'bad',
                                         'error': 'invalid JSON', 'type': 'invalid_tool_call'}])]}}
        history = []
        self.assertEqual(await self.run_graph(InvalidGraph(), history), 'incomplete')
        self.assertEqual(history, [])
        summary = self.events[-1][1]
        self.assertEqual(summary['response_metrics'][0]['invalid_tool_calls'], 1)
        self.assertEqual(summary['tool_requests'], 0)
        self.assertEqual(summary['tokens_reported'], 150)

    async def test_rejected_repair_is_a_completed_conversation_but_blocked_work(self):
        class Graph:
            async def astream(self, *args, **kwargs):
                yield {'model': {'messages': [AIMessage(content='', tool_calls=[{
                    'name': 'run_stage', 'id': 'repair', 'args': {'stage': 'generation'}}])]}}
                yield {'tools': {'messages': [ToolMessage(tool_call_id='repair', content=
                    '{"execution_status":"error","error_code":"REPAIR_EVIDENCE_REQUIRED","data":null}')]}}
                yield {'model': {'messages': [AIMessage(content='修复未执行。')]}}
        status = await self.run_graph(Graph(), [])
        self.assertEqual(status, 'blocked')
        self.assertEqual(self.events[-1][1]['conversation_status'], 'completed')
        self.assertEqual(self.events[-1][1]['workflow_status'], 'no_project')
