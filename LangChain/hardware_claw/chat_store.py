"""Local single-user Chainlit persistence; independent of generated project files."""
import json
import os
import secrets
import shutil
import sqlite3
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from chainlit.data.base import BaseDataLayer
from chainlit.types import PageInfo, PaginatedResponse
from chainlit.user import PersistedUser

ROOT = Path(__file__).resolve().parents[2]


def configure_local_auth():
    path = ROOT / ".secrets" / "chainlit-auth-secret.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as f:
            f.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
    os.environ.setdefault("CHAINLIT_AUTH_SECRET", path.read_text(encoding="utf-8").strip())


def now():
    return datetime.now(timezone.utc).isoformat()


class LocalChatStore(BaseDataLayer):
    def __init__(self, root=None):
        self.root = Path(root) if root else ROOT / "workspace" / ".chat"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "history.sqlite3"
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, thread TEXT, data TEXT, PRIMARY KEY(kind,id))")

    def connect(self):
        return sqlite3.connect(self.db, timeout=10)

    def put(self, kind, key, data, thread=None):
        with self.connect() as con:
            con.execute("INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data, thread=excluded.thread", (kind, key, thread, json.dumps(data, ensure_ascii=False)))

    def get(self, kind, key):
        with self.connect() as con:
            row = con.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row else None

    def rows(self, kind, thread=None):
        with self.connect() as con:
            rows = con.execute("SELECT data FROM records WHERE kind=?" + (" AND thread=?" if thread else "") + " ORDER BY rowid", (kind, thread) if thread else (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def remove(self, kind, key):
        with self.connect() as con:
            con.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, key))

    async def get_user(self, identifier):
        data = self.get("user", identifier)
        return PersistedUser(**data) if data else None

    async def create_user(self, user):
        existing = await self.get_user(user.identifier)
        if existing:
            return existing
        data = dict(id=str(uuid.uuid4()), createdAt=now(), identifier=user.identifier, metadata=user.metadata, display_name=user.display_name)
        self.put("user", user.identifier, data)
        return PersistedUser(**data)

    async def update_thread(self, thread_id, name=None, user_id=None, metadata=None, tags=None):
        data = self.get("thread", thread_id) or dict(id=thread_id, createdAt=now(), name=None, userId=None, userIdentifier=None, metadata={}, tags=[])
        if name is not None:
            data["name"] = name
        if user_id is not None:
            data["userId"] = user_id
            data["userIdentifier"] = next((u["identifier"] for u in self.rows("user") if u["id"] == user_id), None)
        if metadata is not None:
            # Application state is stored separately; never persist runtime objects/env.
            data["metadata"] = {k: v for k, v in metadata.items() if k in {"chat_profile", "chat_settings", "client_type"}}
        if tags is not None:
            data["tags"] = tags
        data["updatedAt"] = now()
        self.put("thread", thread_id, data)

    async def get_thread_author(self, thread_id):
        return (self.get("thread", thread_id) or {}).get("userIdentifier", "")

    async def get_thread(self, thread_id):
        data = self.get("thread", thread_id)
        if data:
            data["steps"] = self.rows("step", thread_id)
            data["elements"] = self.rows("element", thread_id)
        return data

    async def list_threads(self, pagination, filters):
        rows = [t for t in self.rows("thread") if t.get("userId") == filters.userId]
        if filters.search:
            rows = [t for t in rows if filters.search.casefold() in (t.get("name") or "").casefold()]
        if filters.feedback is not None:
            ids = {f.get("threadId") for f in self.rows("feedback") if f["value"] == filters.feedback}
            rows = [t for t in rows if t["id"] in ids]
        rows.sort(key=lambda t: t.get("updatedAt", t["createdAt"]), reverse=True)
        if pagination.cursor:
            index = next((i for i, t in enumerate(rows) if t["id"] == pagination.cursor), None)
            rows = rows[index + 1:] if index is not None else []
        first = max(1, min(pagination.first, 100))
        selected = rows[:first]
        for t in selected:
            t.update(steps=[], elements=[])
        return PaginatedResponse(PageInfo(len(rows) > first, selected[0]["id"] if selected else None, selected[-1]["id"] if selected else None), selected)

    async def delete_thread(self, thread_id):
        # Deleting a chat never deletes a generated project.
        with self.connect() as con:
            con.execute("DELETE FROM records WHERE thread=? OR (kind IN ('thread','state') AND id=?)", (thread_id, thread_id))

    async def create_step(self, step_dict):
        await self.update_step(step_dict)

    async def update_step(self, step_dict):
        data = self.get("step", step_dict["id"]) or {}
        data.update(step_dict)
        self.put("step", data["id"], data, data["threadId"])

    async def delete_step(self, step_id):
        self.remove("step", step_id)

    async def create_element(self, element):
        data = element.to_dict()
        asset = uuid.uuid4().hex
        assets = self.root / "assets"
        assets.mkdir(exist_ok=True)
        target = assets / asset
        if element.path:
            shutil.copyfile(element.path, target)
        elif element.content is not None:
            content = element.content
            target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        else:
            self.put("element", data["id"], data, data["threadId"])
            return
        data.update(url=f"/hardware-claw-assets/{data['threadId']}/{data['id']}", chainlitKey=None, objectKey=asset)
        self.put("element", data["id"], data, data["threadId"])

    async def get_element(self, thread_id, element_id):
        data = self.get("element", element_id)
        return data if data and data["threadId"] == thread_id else None

    async def delete_element(self, element_id, thread_id=None):
        data = self.get("element", element_id)
        if data and (thread_id is None or data["threadId"] == thread_id):
            self.remove("element", element_id)

    async def upsert_feedback(self, feedback):
        data = asdict(feedback)
        data["id"] = data.get("id") or str(uuid.uuid4())
        self.put("feedback", data["id"], data, data.get("threadId"))
        step = self.get("step", data["forId"])
        if step:
            step["feedback"] = data
            await self.update_step(step)
        return data["id"]

    async def delete_feedback(self, feedback_id):
        data = self.get("feedback", feedback_id)
        if data:
            step = self.get("step", data["forId"])
            if step:
                step["feedback"] = None
                await self.update_step(step)
        self.remove("feedback", feedback_id)
        return True

    async def get_favorite_steps(self, user_id):
        owned = {t["id"] for t in self.rows("thread") if t.get("userId") == user_id}
        return [s for s in self.rows("step") if s["threadId"] in owned and (s.get("metadata") or {}).get("favorite")]

    async def build_debug_url(self):
        return ""

    async def close(self):
        pass
