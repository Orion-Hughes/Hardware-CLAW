import asyncio
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from hardware_claw.runtime import execute_turn
from hardware_claw import limits
from test_agent import ScriptedModel


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_followup_change_requires_current_delivery(self):
        from unittest.mock import Mock
        project = Mock()
        project.get.side_effect = [{"version": 1}, {"version": 2}]
        project.delivery.return_value = {"delivery_status": "incomplete", "build": "not_run"}
        class Graph:
            async def astream(self, *args, **kwargs):
                yield {"model": {"messages": [AIMessage(content="修改完成") ]}}
        with patch("hardware_claw.runtime.build_agent", return_value=Graph()):
            status = await execute_turn(None, "把滚动速度改慢", [], self.emit, project=project)
        self.assertEqual(status, "incomplete")
        project.export.assert_not_called()

    async def test_consultation_does_not_force_export(self):
        from unittest.mock import Mock
        project = Mock()
        project.get.return_value = {"version": 1}
        project.delivery.return_value = {"delivery_status": "incomplete", "build": "not_run"}
        class Graph:
            async def astream(self, *args, **kwargs):
                yield {"model": {"messages": [AIMessage(content="这是滚动速度参数") ]}}
        with patch("hardware_claw.runtime.build_agent", return_value=Graph()):
            status = await execute_turn(None, "解释参数", [], self.emit, project=project)
        self.assertEqual(status, "completed")
        project.export.assert_not_called()

    async def test_budget_exit_packages_without_mutating_source(self):
        from unittest.mock import Mock
        project = Mock()
        project.get.return_value = {"version": 3}
        project.delivery.side_effect = [
            {"version":3,"build":"pass","archive":None,"delivery_status":"incomplete"},
            {"version":3,"build":"pass","archive":"test.zip","delivery_status":"ready_for_vscode","behavior":"fail"}]
        class BrokenGraph:
            async def astream(self,*args,**kwargs):
                raise RuntimeError('budget fixture')
                yield {}
        with patch('hardware_claw.runtime.build_agent',return_value=BrokenGraph()):
            status=await execute_turn(None,'generate',[],self.emit,project=project,require_delivery=True)
        self.assertEqual(status,'error')
        project.export.assert_called_once_with(3)
        project.write_files.assert_not_called()
        self.assertEqual(self.events[-1][1]['project']['behavior'],'fail')
        self.assertTrue(self.events[-1][1]['host_packaged'])

    async def asyncSetUp(self):
        self.events = []

    async def emit(self, kind, data):
        self.events.append((kind, data))

    async def test_round_trip_and_unknown_usage(self):
        history = []
        status = await execute_turn(ScriptedModel(), "DHT22", history, self.emit)
        self.assertEqual(status, "completed")
        self.assertEqual(len(history), 2)
        request = next(v for k, v in self.events if k == "tool_request")
        result = next(v for k, v in self.events if k == "tool_result")
        self.assertEqual(request["id"], result["id"])
        self.assertIsNone(self.events[-1][1]["tokens_reported"])
        payload = self.events[-1][1]["tool_payload_characters"]["get_hardware_info"]
        self.assertEqual(payload["requests"], 1)
        self.assertGreater(payload["argument_characters"], 0)
        self.assertGreater(payload["result_characters"], 0)

    async def test_budget_does_not_commit_partial_history(self):
        history = []
        status = await execute_turn(ScriptedModel(loop_forever=True), "loop", history, self.emit)
        self.assertEqual(status, "error")
        self.assertEqual(history, [])
        error = next(v for k, v in self.events if k == "error")
        self.assertIn("调用预算", error["text"])

    async def test_history_bounded_and_isolated(self):
        history = [m for i in range(limits.HISTORY_TURNS + 2) for m in (HumanMessage(content=str(i)), AIMessage(content="old"))]
        other = []
        await execute_turn(ScriptedModel(), "next", history, self.emit)
        self.assertEqual(len(history), 2 * limits.HISTORY_TURNS)
        self.assertEqual(other, [])
        self.assertEqual(history[-2].content, "next")

    async def test_timeout_and_cancel(self):
        class SlowGraph:
            async def astream(self, *args, **kwargs):
                await asyncio.sleep(60)
                yield {}

        with patch("hardware_claw.runtime.build_agent", return_value=SlowGraph()):
            history = []
            status = await execute_turn(None, "slow", history, self.emit, timeout=0.01)
            self.assertEqual(status, "error")
            self.assertEqual(history, [])
            self.assertIn("运行时限", self.events[-2][1]["text"])
            task = asyncio.create_task(execute_turn(None, "cancel", history, self.emit))
            await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(self.events[-1][1]["status"], "cancelled")

    async def test_invalid_tool_json_is_not_completed(self):
        class InvalidGraph:
            async def astream(self, *args, **kwargs):
                yield {"model": {"messages": [AIMessage(content="准备写入", invalid_tool_calls=[{"name": "write_project_files", "args": "{broken", "id": "bad", "error": "invalid JSON", "type": "invalid_tool_call"}])]}}
        with patch("hardware_claw.runtime.build_agent", return_value=InvalidGraph()):
            history = []
            status = await execute_turn(None, "write", history, self.emit)
            self.assertEqual(status, "incomplete")
            self.assertEqual(history, [])

    async def test_model_claim_does_not_prove_delivery(self):
        from unittest.mock import Mock
        class ClaimGraph:
            async def astream(self, *args, **kwargs):
                yield {"model": {"messages": [AIMessage(content="工程已经完成！")]}}
        project = Mock()
        project.get.return_value = {"version": 1}
        project.delivery.return_value = {"delivery_status": "incomplete"}
        with patch("hardware_claw.runtime.build_agent", return_value=ClaimGraph()):
            status = await execute_turn(None, "generate", [], self.emit, project=project, require_delivery=True)
            self.assertEqual(status, "incomplete")

    async def test_truncated_response_metrics_preserved(self):
        class TruncatedGraph:
            async def astream(self, *args, **kwargs):
                yield {"model": {"messages": [AIMessage(
                    content="", response_metadata={"finish_reason": "length"},
                    usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
                    invalid_tool_calls=[{"name": "write_project_files", "args": "{", "id": "bad", "error": "invalid JSON", "type": "invalid_tool_call"}],
                )]}}
        with patch("hardware_claw.runtime.build_agent", return_value=TruncatedGraph()):
            status = await execute_turn(None, "generate", [], self.emit)
        self.assertEqual(status, "incomplete")
        summary = self.events[-1][1]
        self.assertEqual(summary["budget_profile"], limits.snapshot())
        self.assertEqual(summary["input_tokens_reported"], 100)
        self.assertEqual(summary["output_tokens_reported"], 50)
        self.assertEqual(summary["response_metrics"][0]["finish_reason"], "length")
        self.assertEqual(summary["response_metrics"][0]["invalid_tool_calls"], 1)
        self.assertEqual(summary["tool_requests"], 0)
