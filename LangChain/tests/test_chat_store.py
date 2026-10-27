import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import app
from chainlit.types import Pagination, ThreadFilter
from chainlit.user import User
from langchain_core.messages import HumanMessage
from hardware_claw.chat_store import LocalChatStore, ROOT


class ChatStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        root = ROOT / "temp" / "chat-tests"
        root.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(dir=root))
        self.store = LocalChatStore(self.path)
        self.user = await self.store.create_user(User(identifier="local"))

    async def test_reopen_pagination_search_and_owner(self):
        for tid in ("a", "b"):
            await self.store.update_thread(tid, name=f"chat-{tid}", user_id=self.user.id)
            await self.store.create_step(dict(id=f"step-{tid}", threadId=tid, type="user_message", output=tid))
            self.store.put("state", tid, {"project_id": f"project-{tid}"})
        reopened = LocalChatStore(self.path)
        page = await reopened.list_threads(Pagination(first=1), ThreadFilter(userId=self.user.id))
        self.assertTrue(page.pageInfo.hasNextPage)
        next_page = await reopened.list_threads(Pagination(first=1, cursor=page.pageInfo.endCursor), ThreadFilter(userId=self.user.id))
        self.assertNotEqual(page.data[0]["id"], next_page.data[0]["id"])
        self.assertEqual(len((await reopened.list_threads(Pagination(first=10), ThreadFilter(userId="other"))).data), 0)
        self.assertEqual((await reopened.get_thread("a"))["steps"][0]["output"], "a")
        self.assertEqual(reopened.get("state", "b")["project_id"], "project-b")
        await reopened.update_thread("a", metadata={"env": {"SECRET": "excluded"}})
        self.assertEqual(reopened.get("state", "a")["project_id"], "project-a")
        self.assertNotIn("env", (await reopened.get_thread("a"))["metadata"])

    async def test_asset_persistence_and_delete_keeps_project(self):
        await self.store.update_thread("a", user_id=self.user.id)
        asset = SimpleNamespace(path=None, content="saved text", to_dict=lambda: dict(id="e", threadId="a", name="usage.txt", type="text"))
        await self.store.create_element(asset)
        data = await LocalChatStore(self.path).get_element("a", "e")
        self.assertEqual((self.path / "assets" / data["objectKey"]).read_text(), "saved text")
        self.assertIsNone(await self.store.get_element("other", "e"))
        project = self.path / "project-source"
        project.write_text("unchanged")
        await self.store.delete_thread("a")
        self.assertIsNone(await self.store.get_thread("a"))
        self.assertEqual(project.read_text(), "unchanged")

    async def test_resume_restores_exact_binding_and_history(self):
        state = {}
        session = SimpleNamespace(set=state.__setitem__, get=state.get)
        for tid in ("a", "b"):
            self.store.put("state", tid, dict(project_id=f"project-{tid}", mode="generate", history=[dict(role="user", content=tid)]))
        opened = []
        def open_project(pid):
            opened.append(pid)
            return SimpleNamespace(id=pid, get=lambda: {"version": 7})
        with patch.object(app, "chat_store", return_value=LocalChatStore(self.path)), patch.object(app.cl, "user_session", session), patch.object(app.cl, "Message", return_value=SimpleNamespace(send=AsyncMock(), to_dict=lambda: {})), patch.object(app.ProjectService, "open", side_effect=open_project):
            for tid in ("a", "b", "a"):
                await app.resume({"id": tid})
                self.assertEqual(state["project"].id, f"project-{tid}")
                self.assertEqual(state["history"][0].content, tid)
                self.assertIsInstance(state["history"][0], HumanMessage)
        self.assertEqual(opened, ["project-a", "project-b", "project-a"])
