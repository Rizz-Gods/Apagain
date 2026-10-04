from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL = {"succeeded", "failed"}
ACTIVE = {"queued", "running", "blocked"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MissionStateStore:
    """Durable bridge between Console conversations and kernel task execution."""

    def __init__(self, console_db: str | Path):
        self.path = Path(console_db)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS missions (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                goal TEXT NOT NULL,
                strategy TEXT NOT NULL,
                root_task_ids TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL,
                latest_task_id TEXT,
                latest_outcome TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_missions_conversation
                ON missions(conversation_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_missions_status
                ON missions(status, updated_at);
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def create(
        self,
        conversation_id: str,
        goal: str,
        strategy: str,
        mission_id: str | None = None,
    ) -> dict[str, Any]:
        mission_id = mission_id or str(uuid.uuid4())
        now = now_iso()
        self.db.execute(
            """
            INSERT INTO missions
            (id,conversation_id,goal,strategy,root_task_ids,status,
             latest_task_id,latest_outcome,created_at,updated_at,completed_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                mission_id,
                conversation_id,
                goal,
                strategy,
                "[]",
                "queued",
                None,
                "{}",
                now,
                now,
                None,
            ),
        )
        self.db.commit()
        return self.get(mission_id) or {}

    def attach_root_tasks(self, mission_id: str, root_task_ids: list[str]) -> dict[str, Any]:
        now = now_iso()
        self.db.execute(
            "UPDATE missions SET root_task_ids=?, updated_at=? WHERE id=?",
            (json.dumps(root_task_ids), now, mission_id),
        )
        self.db.commit()
        return self.get(mission_id) or {}

    def get(self, mission_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
        return self._row(row) if row else None

    def for_conversation(self, conversation_id: str, limit: int = 8) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT * FROM missions
            WHERE conversation_id=?
            ORDER BY updated_at DESC LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
        return [self._row(row) for row in reversed(rows)]

    def find_by_task(self, task_id: str) -> dict[str, Any] | None:
        rows = self.db.execute("SELECT * FROM missions ORDER BY updated_at DESC").fetchall()
        for row in rows:
            root_ids = json.loads(row["root_task_ids"] or "[]")
            if task_id in root_ids:
                return self._row(row)
        return None

    def update_from_task(
        self,
        mission_id: str,
        task_id: str,
        status: str,
        outcome: dict[str, Any] | None = None,
        task_db: str | Path | None = None,
    ) -> dict[str, Any] | None:
        mission = self.get(mission_id)
        if mission is None:
            return None

        root_ids = list(mission["root_task_ids"])
        aggregate = str(status)
        if task_db and root_ids:
            aggregate = self._aggregate_root_status(root_ids, str(task_db), fallback=aggregate)

        now = now_iso()
        completed_at = mission["completed_at"]
        if aggregate in TERMINAL:
            completed_at = completed_at or now
        else:
            completed_at = None

        self.db.execute(
            """
            UPDATE missions
            SET status=?, latest_task_id=?, latest_outcome=?,
                updated_at=?, completed_at=?
            WHERE id=?
            """,
            (
                aggregate,
                task_id,
                json.dumps(outcome or {}, ensure_ascii=False),
                now,
                completed_at,
                mission_id,
            ),
        )
        self.db.commit()
        return self.get(mission_id)

    def context_for_conversation(self, conversation_id: str, limit: int = 6) -> str:
        missions = self.for_conversation(conversation_id, limit)
        if not missions:
            return ""

        lines = ["DURABLE OTH MISSION STATE:"]
        for mission in missions:
            outcome = mission.get("latest_outcome") or {}
            outcome_summary = outcome.get("summary") or outcome.get("error") or ""
            lines.extend(
                [
                    f"- Mission {mission['id']}",
                    f"  Goal: {mission['goal']}",
                    f"  Strategy: {mission['strategy']}",
                    f"  Status: {mission['status']}",
                    f"  Root tasks: {', '.join(mission['root_task_ids']) or 'none'}",
                    f"  Latest task: {mission['latest_task_id'] or 'none'}",
                    f"  Outcome: {outcome_summary or 'none'}",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "goal": row["goal"],
            "strategy": row["strategy"],
            "root_task_ids": json.loads(row["root_task_ids"] or "[]"),
            "status": row["status"],
            "latest_task_id": row["latest_task_id"],
            "latest_outcome": json.loads(row["latest_outcome"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
        }

    @staticmethod
    def _aggregate_root_status(
        root_ids: list[str],
        task_db: str,
        fallback: str,
    ) -> str:
        path = Path(task_db)
        if not path.exists():
            return fallback
        try:
            conn = sqlite3.connect(path)
            rows = conn.execute(
                "SELECT id,status FROM tasks WHERE id IN (%s)"
                % ",".join("?" for _ in root_ids),
                tuple(root_ids),
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            return fallback

        observed = {str(row[1]) for row in rows}
        if not observed:
            return fallback
        if "running" in observed:
            return "running"
        if "queued" in observed:
            return "queued"
        if "blocked" in observed:
            return "blocked"
        if observed and observed.issubset({"succeeded"}):
            return "succeeded"
        if "failed" in observed:
            return "failed"
        return fallback
