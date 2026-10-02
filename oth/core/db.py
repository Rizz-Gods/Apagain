import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, capability TEXT NOT NULL, action TEXT NOT NULL,
  payload TEXT NOT NULL, priority INTEGER NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY, name TEXT NOT NULL,
  capabilities TEXT NOT NULL, status TEXT NOT NULL, metadata TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, kind TEXT NOT NULL,
  payload TEXT NOT NULL, created_at TEXT NOT NULL
);
"""

class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def add_event(self, task_id: str | None, kind: str, payload: dict[str, Any], created_at: str):
        self.conn.execute(
            "INSERT INTO events(task_id,kind,payload,created_at) VALUES(?,?,?,?)",
            (task_id, kind, json.dumps(payload), created_at),
        )
        self.conn.commit()

    def add_task(self, task):
        self.conn.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)",
            (task.id, task.capability, task.action, json.dumps(task.payload),
             task.priority, task.status, task.created_at, task.created_at),
        )
        self.conn.commit()

    def update_task(self, task_id: str, status: str, updated_at: str):
        self.conn.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (status, updated_at, task_id),
        )
        self.conn.commit()

    def list_tasks(self):
        return self.conn.execute(
            "SELECT * FROM tasks ORDER BY priority DESC, created_at ASC"
        ).fetchall()

    def close(self):
        self.conn.close()
