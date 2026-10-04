import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class ConsoleStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            mission_id TEXT NOT NULL DEFAULT 'primary'
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def create_conversation(self, conversation_id: str, title: str = "New Mission Chat", mission_id: str = "primary"):
        now = now_iso()
        self.db.execute(
            "INSERT INTO conversations(id,title,created_at,updated_at,mission_id) VALUES(?,?,?,?,?)",
            (conversation_id, title, now, now, mission_id),
        )
        self.db.commit()
        return dict(self.get_conversation(conversation_id))

    def get_conversation(self, conversation_id: str):
        return self.db.execute(
            "SELECT * FROM conversations WHERE id=?", (conversation_id,)
        ).fetchone()

    def list_conversations(self, limit: int = 50):
        rows = self.db.execute(
            "SELECT * FROM conversations WHERE archived=0 ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_message(self, conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None):
        now = now_iso()
        self.db.execute(
            "INSERT INTO messages(conversation_id,role,content,metadata,created_at) VALUES(?,?,?,?,?)",
            (conversation_id, role, content, json.dumps(metadata or {}, ensure_ascii=False), now),
        )
        self.db.execute(
            "UPDATE conversations SET updated_at=? WHERE id=?",
            (now, conversation_id),
        )
        self.db.commit()

    def messages(self, conversation_id: str, limit: int = 40):
        rows = self.db.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        rows = list(reversed(rows))
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def stats(self):
        return {
            "conversations": self.db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            "messages": self.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        }
