"""UI-independent task records. SQLite transactions serialize state changes."""
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class WorkflowError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else ROOT / 'workspace/.tasks'
        for path in (self.root, *self.root.parents):
            if path.is_symlink() or path.is_junction():
                raise WorkflowError('UNSAFE_TASK_PATH', '任务目录不能是链接。')
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'coordinator.sqlite3'
        if self.db.is_symlink() or (self.db.exists() and self.db.stat().st_nlink > 1):
            raise WorkflowError('UNSAFE_TASK_PATH', '任务数据库不能是链接。')
        with self.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, data TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=10)
        try:
            with con:
                yield con
        finally:
            con.close()

    def create(self, project_id=None):
        ident = uuid.uuid4().hex
        state = {'schema_version': 1, 'task_id': ident, 'version': 0, 'project_id': project_id,
                 'created_at': timestamp(), 'original_request': None, 'current_request': None,
                 'active_run': None, 'latest': {}, 'recent_runs': [], 'latest_outcome': 'idle',
                 'turn_count': 0, 'stage_attempts': 0,
                 'usage': {'model_responses': 0, 'input_tokens': 0, 'output_tokens': 0,
                           'total_tokens': 0, 'missing_usage_responses': 0}}
        with self.connect() as con:
            con.execute('INSERT INTO tasks VALUES (?, ?)', (ident, json.dumps(state, ensure_ascii=False)))
        return ident

    def _load(self, con, task_id):
        if not isinstance(task_id, str) or not re.fullmatch('[a-f0-9]{32}', task_id):
            raise WorkflowError('INVALID_TASK', '任务ID格式不合法。')
        row = con.execute('SELECT data FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise WorkflowError('TASK_NOT_FOUND', '任务记录不存在。')
        return json.loads(row[0])

    def load(self, task_id):
        with self.connect() as con:
            return self._load(con, task_id)

    @contextmanager
    def edit(self, task_id):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            state = self._load(con, task_id)
            yield state, con
            state['version'] += 1
            con.execute('UPDATE tasks SET data=? WHERE id=?', (json.dumps(state, ensure_ascii=False), task_id))

    @staticmethod
    def save_record(con, task_id, record):
        con.execute('INSERT INTO records VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                    (record['run_id'], task_id, json.dumps(record, ensure_ascii=False)))

    def record(self, task_id, ref):
        if not isinstance(ref, str) or not re.fullmatch('[a-f0-9]{32}', ref):
            raise WorkflowError('INVALID_REFERENCE', '只接受本任务的交接ID。')
        with self.connect() as con:
            row = con.execute('SELECT data FROM records WHERE id=? AND task_id=?', (ref, task_id)).fetchone()
        if not row:
            raise WorkflowError('INVALID_REFERENCE', '该交接不属于当前任务。')
        return json.loads(row[0])
