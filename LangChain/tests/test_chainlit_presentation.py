import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from hardware_claw.web import ToolTimeline


class FakeStep:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = kwargs.get("id", f"step-{id(self)}")
        self.input = ""
        self.output = ""
        self.language = None
        self.send = AsyncMock()
        self.update = AsyncMock()


class ChainlitPresentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_steps_are_children_of_one_collapsed_parent(self):
        calls = []
        timeline = ToolTimeline(
            lambda **kwargs: calls.append(FakeStep(**kwargs)) or calls[-1],
            lambda: "2026-11-10T00:00:00+00:00",
            root_parent_id="on-message",
        )

        first = await timeline.start_tool("call-1", "search_hardware", {"query": "dht22"})
        second = await timeline.start_tool("call-2", "get_hardware_info", {"id": "dht22"})
        await timeline.finish_tool("call-1", '{"status":"ok"}')
        await timeline.finish_tool("call-2", '{"status":"ok"}')
        await timeline.finish()

        parent, tool_a, tool_b = calls
        self.assertEqual(parent.name, "工具执行过程")
        self.assertEqual(parent.type, "run")
        self.assertEqual(parent.parent_id, "on-message")
        self.assertFalse(parent.default_open)
        self.assertTrue(parent.auto_collapse)
        self.assertIs(tool_a.parent_id, parent.id)
        self.assertIs(tool_b.parent_id, parent.id)
        self.assertEqual(tool_a.input, {"query": "dht22"})
        self.assertEqual(tool_b.output, "{\"status\":\"ok\"}")
        self.assertEqual(parent.output, "工具执行结束：2 次调用，2 次返回")
        self.assertEqual(parent.send.await_count, 1)
        self.assertGreaterEqual(parent.update.await_count, 3)


if __name__ == "__main__":
    unittest.main()
