"""Exercise the real Chainlit handler without paid API calls or file creation."""
import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import app
from hardware_claw.coordinator import TaskStore
from hardware_claw.coordinator.store import ROOT


class WebRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = {}
        session = Mock()
        session.get.side_effect = self.state.get
        session.set.side_effect = self.state.__setitem__
        self.project = Mock(id="test-project")
        self.project.get.return_value = {"version": 1}
        base = ROOT / 'temp' / 'web-routing-tests'
        base.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(tmp.cleanup)
        self.store = TaskStore(Path(tmp.name))
        self.patches = [
            patch.object(app.cl, "user_session", session),
            patch.object(app.cl, "Message", return_value=SimpleNamespace(send=AsyncMock())),
            patch.object(app.ProjectService, "create", return_value=self.project),
            patch.object(app.ProjectService, "open", return_value=self.project),
            patch.object(app, "create_model", return_value=object()),
            patch.object(app, "execute_turn", new_callable=AsyncMock),
            patch.object(app, "save_chat", new_callable=AsyncMock),
            patch.object(app, 'TaskStore', return_value=self.store),
        ]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)
        self.create = self.mocks[2]
        self.execute = self.mocks[5]

    async def send(self, content):
        await app.respond(SimpleNamespace(content=content))

    async def test_default_routes_to_coordinator_and_followup_reuses(self):
        await app.start()
        self.create.assert_not_called()
        async def generate(*args, coordinator, **kwargs):
            with self.store.edit(coordinator.task_id) as (state, _):
                state['project_id'] = self.project.id
            coordinator.project = self.project
        self.execute.side_effect = generate
        await self.send("ESP32屏幕滚动显示Hello")
        task_id = self.execute.call_args.kwargs['coordinator'].task_id
        self.execute.side_effect = None
        await self.send("把文字颜色改为红色")
        self.create.assert_not_called()
        coordinator = self.execute.call_args.kwargs['coordinator']
        self.assertEqual(coordinator.task_id, task_id)
        self.assertIs(coordinator.project, self.project)

    async def test_removed_modes_and_new_task(self):
        await app.start()
        await self.send("/query")
        await self.send("/coordinator")
        self.execute.assert_not_called()
        await self.send("有哪些屏幕")
        ident = self.state['coordinator_task_id']
        self.assertIsNone(self.execute.call_args.kwargs['coordinator'].project)
        await self.send("/new 屏幕显示Hello")
        self.assertNotEqual(self.state['coordinator_task_id'], ident)
        self.assertEqual(self.execute.call_args.args[1], '屏幕显示Hello')
        self.create.assert_not_called()

    async def test_empty_and_unknown_commands_do_not_call_model(self):
        await app.start()
        await self.send("  ")
        await self.send("/new")
        await self.send("/unknown")
        self.create.assert_not_called()
        self.execute.assert_not_called()

    async def test_deployment_commands_are_host_only_and_do_not_create_a_model(self):
        await app.start()
        with patch.object(app, "preview_command", new_callable=AsyncMock, return_value="preview only") as preview:
            await self.send("/ports")
            await self.send("/flash-plan")
        self.assertEqual(preview.await_count, 2)
        self.execute.assert_not_called()
        app.create_model.assert_not_called()

    async def test_resume_does_not_create_project(self):
        await app.start()
        await self.send("/project test-project")
        await self.send("检查工程")
        self.create.assert_not_called()
        self.assertIs(self.execute.call_args.kwargs['coordinator'].project, self.project)

    async def test_mcp_preview_uses_verified_path_and_ignores_null_artifacts(self):
        parent = SimpleNamespace(id="parent-step", send=AsyncMock(), update=AsyncMock())
        step = SimpleNamespace(name="read_task_evidence", send=AsyncMock(), update=AsyncMock())
        async def execute(model, question, history, emit, **kwargs):
            await emit("tool_request", {"id":"image-call", "name":"read_task_evidence", "args":{"kind":"simulation"}})
            await emit("tool_result", {"id":"image-call", "content":json.dumps({"data":{
                "version":1,"attempt":"a"*32,"evidence_directory":"untrusted-path",
                "filename":"screenshot-001.png", "image":{"width":10,"height":10}}})})
        self.execute.side_effect = execute
        await self.send('/project test-project')
        with patch.object(app.cl,"Step",side_effect=[parent, step]), patch.object(app.cl,"Image") as image, patch('hardware_claw.adapters.wokwi_mcp.read_evidence',return_value={"image_path":"verified.png"}) as read:
            await self.send("查看截图")
            self.assertEqual(parent.output, "工具调用 1 次，已返回 1 次")
            self.assertEqual(step.language, "json")
            read.assert_called_once_with(self.project,1,"a"*32,"screenshot-001.png")
            image.assert_called_once_with(name="screenshot-001.png",path="verified.png",display="inline")
