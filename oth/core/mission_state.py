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
            aggregate = self._aggregate_task_graph(root_ids, str(task_db), fallback=aggregate)

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

    def reconcile(self, task_db: str | Path) -> dict[str, int]:
        """Reconcile durable mission rows with the authoritative task graph."""
        rows = self.db.execute("SELECT * FROM missions ORDER BY updated_at ASC").fetchall()
        checked = 0
        changed = 0
        for row in rows:
            mission = self._row(row)
            roots = mission["root_task_ids"]
            if not roots:
                continue
            checked += 1
            aggregate = self._aggregate_task_graph(roots, str(task_db), fallback=mission["status"])
            graph = self.graph_for_mission(mission["id"], task_db)
            nodes = graph.get("nodes", [])
            latest = max(nodes, key=lambda node: str(node.get("updated_at", "")), default=None)
            latest_task_id = (latest or {}).get("id") or mission["latest_task_id"]
            should_complete = aggregate in TERMINAL
            completed_at = mission["completed_at"] if should_complete else None
            if aggregate == mission["status"] and completed_at == mission["completed_at"] and latest_task_id == mission["latest_task_id"]:
                continue
            outcome = dict(mission["latest_outcome"] or {})
            outcome["reconciled"] = True
            outcome["graph_status"] = aggregate
            self.db.execute(
                "UPDATE missions SET status=?, latest_task_id=?, latest_outcome=?, updated_at=?, completed_at=? WHERE id=?",
                (
                    aggregate,
                    latest_task_id,
                    json.dumps(outcome, ensure_ascii=False),
                    now_iso(),
                    completed_at,
                    mission["id"],
                ),
            )
            changed += 1
        self.db.commit()
        return {"checked": checked, "changed": changed}

    def graph_for_mission(self, mission_id: str, task_db: str | Path) -> dict[str, Any]:
        mission = self.get(mission_id)
        if mission is None:
            return {"mission_id": mission_id, "roots": [], "nodes": [], "edges": [], "counts": {"total": 0}}
        path = Path(task_db)
        if not path.exists():
            return {"mission_id": mission_id, "roots": mission["root_task_ids"], "nodes": [], "edges": [], "counts": {"total": 0}}
        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            roots = list(mission["root_task_ids"])
            queue = [(root, 0) for root in roots]
            seen: set[str] = set(roots)
            nodes: dict[str, dict[str, Any]] = {}
            edges: list[dict[str, Any]] = []
            while queue and len(nodes) < 512:
                current, level = queue.pop(0)
                row = conn.execute(
                    "SELECT id, capability, action, status, priority, created_at, updated_at FROM tasks WHERE id=?",
                    (current,),
                ).fetchone()
                if row:
                    nodes[current] = {**dict(row), "level": level}
                children = conn.execute(
                    "SELECT child_task_id, edge_type FROM task_edges WHERE parent_task_id=?",
                    (current,),
                ).fetchall()
                for child in children:
                    child_id = str(child["child_task_id"])
                    edges.append({
                        "parent_task_id": current,
                        "child_task_id": child_id,
                        "edge_type": child["edge_type"],
                    })
                    if child_id not in seen:
                        seen.add(child_id)
                        queue.append((child_id, level + 1))
            conn.close()
        except sqlite3.Error:
            return {"mission_id": mission_id, "roots": mission["root_task_ids"], "nodes": [], "edges": [], "counts": {"total": 0}}

        statuses = [str(node["status"]) for node in nodes.values()]
        counts = {
            "total": len(nodes),
            "queued": statuses.count("queued"),
            "running": statuses.count("running"),
            "blocked": statuses.count("blocked"),
            "succeeded": statuses.count("succeeded"),
            "failed": statuses.count("failed"),
        }
        return {
            "mission_id": mission_id,
            "roots": roots,
            "nodes": list(nodes.values()),
            "edges": edges,
            "counts": counts,
        }

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
                    f"  Task graph: {self._graph_summary(mission['root_task_ids'])}",
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

    def _graph_summary(self, root_ids: list[str]) -> str:
        # Context rendering is intentionally lightweight; detailed graph state is
        # available through the mission API and task graph endpoint.
        return f"{len(root_ids)} root task(s) tracked"

    @staticmethod
    def _aggregate_task_graph(
        root_ids: list[str],
        task_db: str,
        fallback: str,
    ) -> str:
        path = Path(task_db)
        if not path.exists():
            return fallback
        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            queue = list(root_ids)
            seen = set(root_ids)
            task_ids = []
            while queue:
                current = queue.pop(0)
                task_ids.append(current)
                children = conn.execute(
                    "SELECT child_task_id FROM task_edges WHERE parent_task_id=?",
                    (current,),
                ).fetchall()
                for child in children:
                    child_id = str(child[0])
                    if child_id not in seen:
                        seen.add(child_id)
                        queue.append(child_id)
            if not task_ids:
                conn.close()
                return fallback
            rows = conn.execute(
                "SELECT id,status FROM tasks WHERE id IN (%s)"
                % ",".join("?" for _ in task_ids),
                tuple(task_ids),
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            return fallback

        observed = {str(row["status"]) for row in rows}
        if not observed:
            return fallback
        if "running" in observed:
            return "running"
        if "queued" in observed:
            return "queued"
        if "blocked" in observed:
            return "blocked"
        if "failed" in observed:
            return "failed"
        if observed and observed.issubset({"succeeded"}):
            return "succeeded"
        return fallback
