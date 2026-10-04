import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mission_state import MissionStateStore

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "then",
    "have", "will", "your", "what", "when", "where", "which", "about",
    "only", "must", "need", "make", "just", "they", "them", "our",
    "its", "are", "was", "were", "you", "a", "an", "to", "of", "in",
    "on", "is", "be", "as", "by", "it",
}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def tokens(text: str) -> list[str]:
    return [
        token for token in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())
        if token not in STOPWORDS
    ]

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
        CREATE TABLE IF NOT EXISTS conversation_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            source_start INTEGER,
            source_end INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(conversation_id, kind, source_start, source_end)
        );
        CREATE INDEX IF NOT EXISTS idx_memory_conv ON conversation_memory(conversation_id, id);
        CREATE TABLE IF NOT EXISTS compaction_checkpoints (
            conversation_id TEXT PRIMARY KEY,
            last_compacted_message_id INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """)
        self._fts_enabled = True
        try:
            self.db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS message_fts "
                "USING fts5(message_id UNINDEXED, conversation_id UNINDEXED, content)"
            )
        except sqlite3.OperationalError:
            self._fts_enabled = False
        if self._fts_enabled:
            try:
                indexed = self.db.execute("SELECT COUNT(*) FROM message_fts").fetchone()[0]
                if indexed == 0:
                    self.db.execute(
                        "INSERT INTO message_fts(message_id,conversation_id,content) "
                        "SELECT id,conversation_id,content FROM messages"
                    )
            except sqlite3.OperationalError:
                self._fts_enabled = False
        self.db.commit()
        self.missions = MissionStateStore(self.path)

    def close(self):
        self.missions.close()
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
        return self.db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()

    def list_conversations(self, limit: int = 50):
        rows = self.db.execute(
            "SELECT * FROM conversations WHERE archived=0 ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_message(self, conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None):
        now = now_iso()
        cursor = self.db.execute(
            "INSERT INTO messages(conversation_id,role,content,metadata,created_at) VALUES(?,?,?,?,?)",
            (conversation_id, role, content, json.dumps(metadata or {}, ensure_ascii=False), now),
        )
        message_id = cursor.lastrowid
        if self._fts_enabled:
            try:
                self.db.execute(
                    "INSERT INTO message_fts(message_id,conversation_id,content) VALUES(?,?,?)",
                    (message_id, conversation_id, content),
                )
            except sqlite3.OperationalError:
                self._fts_enabled = False
        self.db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))
        self.db.commit()
        self.maybe_compact(conversation_id)

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
        }

    def messages(self, conversation_id: str, limit: int = 40):
        rows = self.db.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        return [self._row_to_message(row) for row in reversed(rows)]

    def search_messages(self, conversation_id: str, query: str, limit: int = 8):
        query_tokens = tokens(query)
        if not query_tokens:
            return []
        scored: list[tuple[int, int, dict[str, Any]]] = []
        if self._fts_enabled:
            fts_query = " OR ".join(query_tokens[:12])
            try:
                rows = self.db.execute(
                    """
                    SELECT m.* FROM message_fts f
                    JOIN messages m ON m.id=f.message_id
                    WHERE f.conversation_id=? AND message_fts MATCH ?
                    ORDER BY m.id DESC LIMIT ?
                    """,
                    (conversation_id, fts_query, limit * 3),
                ).fetchall()
                for row in rows:
                    content_tokens = set(tokens(row["content"]))
                    score = sum(2 for token in query_tokens if token in content_tokens)
                    scored.append((score, row["id"], self._row_to_message(row)))
            except sqlite3.OperationalError:
                pass
        if not scored:
            rows = self.db.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 250",
                (conversation_id,),
            ).fetchall()
            query_set = set(query_tokens)
            for row in rows:
                score = len(query_set & set(tokens(row["content"])))
                if score:
                    scored.append((score, row["id"], self._row_to_message(row)))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[:limit]]

    def memory(self, conversation_id: str, limit: int = 8):
        rows = self.db.execute(
            """
            SELECT kind, content, source_start, source_end, created_at
            FROM conversation_memory WHERE conversation_id=?
            ORDER BY id DESC LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def _checkpoint(self, conversation_id: str) -> int:
        row = self.db.execute(
            "SELECT last_compacted_message_id FROM compaction_checkpoints WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
        return int(row["last_compacted_message_id"]) if row else 0

    def maybe_compact(self, conversation_id: str, keep_recent: int = 24, threshold: int = 36):
        total = self.db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()[0]
        if total < threshold:
            return
        rows = self.db.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
        cutoff_index = max(0, len(rows) - keep_recent)
        older = rows[:cutoff_index]
        if not older:
            return
        start_id, end_id = older[0]["id"], older[-1]["id"]
        if end_id <= self._checkpoint(conversation_id):
            return

        user_goals, outcomes, seen = [], [], set()
        for row in older:
            content = re.sub(r"\s+", " ", row["content"].strip())
            if not content:
                continue
            if row["role"] == "user":
                compact = content if len(content) <= 420 else content[:417] + "..."
                if compact.lower() not in seen:
                    user_goals.append(compact)
                    seen.add(compact.lower())
            else:
                metadata = {}
                try:
                    metadata = json.loads(row["metadata"] or "{}")
                except Exception:
                    pass
                if metadata.get("mission") or metadata.get("provider") == "oth-kernel":
                    outcomes.append(content if len(content) <= 420 else content[:417] + "...")

        checkpoint_text = (
            "Durable conversation checkpoint\n"
            f"Range: messages {start_id}-{end_id}\n"
            "Operator goals:\n"
            + ("\n".join(f"- {item}" for item in user_goals[-12:]) or "- none")
            + "\nExecution outcomes:\n"
            + ("\n".join(f"- {item}" for item in outcomes[-12:]) or "- none")
        )
        now = now_iso()
        self.db.execute(
            """
            INSERT OR REPLACE INTO conversation_memory
            (conversation_id,kind,content,source_start,source_end,created_at)
            VALUES(?,?,?,?,?,?)
            """,
            (conversation_id, "checkpoint", checkpoint_text, start_id, end_id, now),
        )
        self.db.execute(
            """
            INSERT OR REPLACE INTO compaction_checkpoints
            (conversation_id,last_compacted_message_id,updated_at)
            VALUES(?,?,?)
            """,
            (conversation_id, end_id, now),
        )
        self.db.commit()

    def context_for_model(self, conversation_id: str, query: str, recent: int = 16, retrieved: int = 8, memories: int = 6):
        memory_rows = self.memory(conversation_id, memories)
        recent_messages = self.messages(conversation_id, recent)
        recent_ids = {item["id"] for item in recent_messages}
        retrieved_messages = [
            item for item in self.search_messages(conversation_id, query, retrieved)
            if item["id"] not in recent_ids
        ]
        blocks = []
        mission_context = self.missions.context_for_conversation(conversation_id, memories)
        if mission_context:
            blocks.append({
                "role": "system",
                "content": mission_context,
            })
        if memory_rows:
            blocks.append({
                "role": "system",
                "content": "DURABLE OTH MISSION MEMORY:\n" + "\n\n".join(item["content"] for item in memory_rows),
            })
        if retrieved_messages:
            blocks.append({
                "role": "system",
                "content": "RELEVANT OLDER CONVERSATION:\n" + "\n\n".join(
                    f"{item['role'].upper()}: {item['content']}" for item in retrieved_messages
                ),
            })
        blocks.extend({"role": item["role"], "content": item["content"]} for item in recent_messages)
        return blocks

    def stats(self):
        return {
            "conversations": self.db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            "messages": self.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
            "memory_checkpoints": self.db.execute("SELECT COUNT(*) FROM conversation_memory").fetchone()[0],
            "missions": self.db.execute("SELECT COUNT(*) FROM missions").fetchone()[0],
        }
