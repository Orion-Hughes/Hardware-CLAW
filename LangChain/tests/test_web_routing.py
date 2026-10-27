"""Exercise the real Chainlit handler without paid API calls or file creation."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import app


class WebRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = {}
        session = Mock()
        session.get.side_effect = self.state.get
        session.set.side_effect = self.state.__setitem__
        self.project = Mock(id="test-project")
        self.project.get.return_value = {"version": 1}
        self.patches = [
            patch.object(app.cl, "user_session", session),
            patch.object(app.cl, "Message", return_value=SimpleNamespace(send=AsyncMock())),
            patch.object(app.ProjectService, "create", return_value=self.project),
            patch.object(app.ProjectService, "open", return_value=self.project),
            patch.object(app, "create_model", return_value=object()),
            patch.object(app, "execute_turn", new_callable=AsyncMock),
            patch.object(app, "save_chat", new_callable=AsyncMock),
        ]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)
        self.create = self.mocks[2]
        self.execute = self.mocks[5]

    async def send(self, content):
        await app.respond(SimpleNamespace(content=content))

    async def test_default_creates_vscode_and_followup_reuses(self):
        await app.start()
        self.create.assert_not_called()
        await self.send("ESP32屏幕滚动显示Hello")
        self.create.assert_called_once_with("web-project", "ESP32屏幕滚动显示Hello", "vscode")
        self.assertIs(self.execute.call_args.kwargs["project"], self.project)
        self.assertTrue(self.execute.call_args.kwargs["require_delivery"])
        await self.send("把文字颜色改为红色")
        self.assertEqual(self.create.call_count, 1)
        self.assertIs(self.execute.call_args.kwargs["project"], self.project)

    async def test_query_is_sticky_until_explicit_new(self):
        await app.start()
        await self.send("/query")
        await self.send("有哪些屏幕")
        self.create.assert_not_called()
        self.assertIsNone(self.execute.call_args.kwargs["project"])
        await self.send("/new 屏幕显示Hello")
        self.assertEqual(self.state["mode"], "generate")
        self.assertIs(self.execute.call_args.kwargs["project"], self.project)

    async def test_empty_and_unknown_commands_do_not_call_model(self):
        await app.start()
        await self.send("  ")
        await self.send("/new")
        await self.send("/unknown")
        self.create.assert_not_called()
        self.execute.assert_not_called()

    async def test_resume_does_not_create_project(self):
        await app.start()
        await self.send("/project test-project")
        await self.send("检查工程")
        self.create.assert_not_called()
        self.assertIs(self.execute.call_args.kwargs["project"], self.project)
