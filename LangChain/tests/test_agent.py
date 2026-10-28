import unittest
from pydantic import PrivateAttr
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from hardware_claw.agent import MODEL_CALL_LIMIT, build_agent
from hardware_claw import limits
from hardware_claw.tools.hardware_info import get_board_info


class ScriptedModel(BaseChatModel):
    """Offline test double; never sends a network request."""
    loop_forever: bool = False
    _count: int = PrivateAttr(default=0)

    @property
    def _llm_type(self):
        return "offline-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._count += 1
        if self._count == 1 or self.loop_forever:
            msg = AIMessage(content="", tool_calls=[{
                "name": "get_hardware_info", "args": {"hardware_id": "dht22_red_module"},
                "id": f"call-{self._count}", "type": "tool_call",
            }])
        else:
            assert any(isinstance(m, ToolMessage) for m in messages)
            msg = AIMessage(content="DHT22 profile read; simulation not run.")
        return ChatResult(generations=[ChatGeneration(message=msg)])


class AgentTests(unittest.TestCase):
    def test_known_profile(self):
        result = get_board_info.invoke({"board_id": "esp32-s3-demo"})
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["verified_for_wiring"])

    def test_unknown_profile(self):
        self.assertEqual(get_board_info.invoke({"board_id": "unknown"})["status"], "not_found")

    def test_tool_round_trip(self):
        result = build_agent(ScriptedModel()).invoke({"messages": [("user", "query board")]})
        self.assertTrue(any(isinstance(m, ToolMessage) for m in result["messages"]))
        self.assertEqual(result["messages"][-1].content, "DHT22 profile read; simulation not run.")

    def test_loop_limit(self):
        model = ScriptedModel(loop_forever=True)
        with self.assertRaises(Exception) as caught:
            build_agent(model).invoke({"messages": [("user", "loop")]}, {"recursion_limit": limits.QUERY_GRAPH_STEPS})
        self.assertIn("limit", str(caught.exception).lower())
        self.assertLessEqual(model._count, MODEL_CALL_LIMIT)


if __name__ == "__main__":
    unittest.main()
