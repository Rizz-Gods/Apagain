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
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
  key TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_stats (
  agent_id TEXT PRIMARY KEY, successes INTEGER NOT NULL DEFAULT 0,
  failures INTEGER NOT NULL DEFAULT 0, last_error TEXT,
  last_run TEXT
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

    def add_memory(self, kind: str, key: str, content: dict[str, Any], created_at: str):
        self.conn.execute(
            "INSERT INTO memories(kind,key,content,created_at) VALUES(?,?,?,?)",
            (kind, key, json.dumps(content), created_at),
        )
        self.conn.commit()

    def recent_memories(self, key: str | None = None, limit: int = 5):
        if key:
            return self.conn.execute(
                "SELECT * FROM memories WHERE key=? ORDER BY id DESC LIMIT ?",
                (key, limit),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM memories ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def record_agent_result(self, agent_id: str, success: bool,
                            error: str | None, created_at: str):
        row = self.conn.execute(
            "SELECT successes, failures FROM agent_stats WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
        if row:
            successes = row["successes"] + (1 if success else 0)
            failures = row["failures"] + (0 if success else 1)
            self.conn.execute(
                "UPDATE agent_stats SET successes=?, failures=?, last_error=?, last_run=? WHERE agent_id=?",
                (successes, failures, error, created_at, agent_id),
            )
        else:
            self.conn.execute(
                "INSERT INTO agent_stats(agent_id,successes,failures,last_error,last_run) VALUES(?,?,?,?,?)",
                (agent_id, int(success), int(not success), error, created_at),
            )
        self.conn.commit()

    def agent_health(self, agent_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM agent_stats WHERE agent_id=?", (agent_id,)
        ).fetchone()
        if not row:
            return {"successes": 0, "failures": 0, "reliability": 1.0}
        total = row["successes"] + row["failures"]
        reliability = row["successes"] / total if total else 1.0
        return {
            "successes": row["successes"],
            "failures": row["failures"],
            "reliability": reliability,
            "last_error": row["last_error"],
            "last_run": row["last_run"],
        }

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

    def get_task(self, task_id: str):
        return self.conn.execute(
            "SELECT * FROM tasks WHERE id=?", (task_id,)
        ).fetchone()

    def update_task_payload(self, task_id: str, payload: dict[str, Any], updated_at: str):
        self.conn.execute(
            "UPDATE tasks SET payload=?, updated_at=? WHERE id=?",
            (json.dumps(payload), updated_at, task_id),
        )
        self.conn.commit()

    def list_tasks(self):
        return self.conn.execute(
            "SELECT * FROM tasks ORDER BY priority DESC, created_at ASC"
        ).fetchall()

    def close(self):
        self.conn.close()
