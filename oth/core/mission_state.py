from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL = {"succeeded", "failed", "cancelled"}
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
            CREATE TABLE IF NOT EXISTS mission_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL,
                task_id TEXT,
                kind TEXT NOT NULL,
                status TEXT,
                payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mission_timeline_mission
                ON mission_timeline(mission_id, id);
            CREATE TABLE IF NOT EXISTS mission_attention (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL,
                task_id TEXT,
                severity TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                acknowledged_at TEXT,
                acknowledged_by TEXT,
                dedupe_key TEXT NOT NULL UNIQUE
            );
            CREATE INDEX IF NOT EXISTS idx_mission_attention_mission
                ON mission_attention(mission_id, status, id);
            CREATE INDEX IF NOT EXISTS idx_mission_attention_status
                ON mission_attention(status, id);
            CREATE TABLE IF NOT EXISTS mission_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL,
                task_id TEXT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                prev_hash TEXT,
                entry_hash TEXT NOT NULL UNIQUE
            );
            CREATE INDEX IF NOT EXISTS idx_mission_audit_mission
                ON mission_audit(mission_id, id);
            CREATE INDEX IF NOT EXISTS idx_mission_audit_action
                ON mission_audit(action, id);
            CREATE TABLE IF NOT EXISTS mission_policy_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                policy_json TEXT NOT NULL,
                policy_hash TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(mission_id, revision)
            );
            CREATE INDEX IF NOT EXISTS idx_mission_policy_mission
                ON mission_policy_revisions(mission_id, revision);
            CREATE TABLE IF NOT EXISTS mission_integrity_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                violations_json TEXT NOT NULL DEFAULT '[]',
                fingerprint TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mission_integrity_mission
                ON mission_integrity_checks(mission_id, id);
            """
        )
        existing_columns = {
            row["name"]
            for row in self.db.execute("PRAGMA table_info(missions)").fetchall()
        }
        migrations = (
            ("deadline_at", "TEXT"),
            ("watchdog_status", "TEXT NOT NULL DEFAULT 'ok'"),
            ("watchdog_checked_at", "TEXT"),
            ("escalation_level", "TEXT NOT NULL DEFAULT 'normal'"),
            ("escalation_warning_seconds", "REAL NOT NULL DEFAULT 900"),
            ("escalation_critical_seconds", "REAL NOT NULL DEFAULT 300"),
            ("escalation_checked_at", "TEXT"),
            ("max_tasks", "INTEGER NOT NULL DEFAULT 256"),
            ("max_retries", "INTEGER NOT NULL DEFAULT 8"),
            ("budget_status", "TEXT NOT NULL DEFAULT 'ok'"),
            ("budget_checked_at", "TEXT"),
            ("policy_revision", "INTEGER NOT NULL DEFAULT 1"),
            ("policy_hash", "TEXT"),
            ("approval_external", "INTEGER NOT NULL DEFAULT 1"),
            ("approval_financial", "INTEGER NOT NULL DEFAULT 1"),
            ("cancellation_mode", "TEXT NOT NULL DEFAULT 'graceful'"),
        )
        for column, definition in migrations:
            if column not in existing_columns:
                self.db.execute(
                    f"ALTER TABLE missions ADD COLUMN {column} {definition}"
                )
        self.db.commit()
        self._backfill_policy_revisions()

    def close(self) -> None:
        self.db.close()

    def _default_policy_config(self) -> dict[str, Any]:
        path = self.path.parent.parent / "config" / "policies.json"
        default = {
            "external_actions_require_approval": True,
            "financial_actions_require_approval": True,
        }
        if not path.exists():
            return default
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            return {**default, **loaded} if isinstance(loaded, dict) else default
        except (OSError, ValueError, TypeError):
            return default

    def _policy_document(
        self,
        mission: dict[str, Any],
        approval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        approval = approval or {
            "external_actions_require_approval": bool(mission.get("approval_external", True)),
            "financial_actions_require_approval": bool(mission.get("approval_financial", True)),
        }
        return {
            "approval": {
                "external_actions_require_approval": bool(
                    approval.get("external_actions_require_approval", True)
                ),
                "financial_actions_require_approval": bool(
                    approval.get("financial_actions_require_approval", True)
                ),
            },
            "deadline": {"deadline_at": mission.get("deadline_at")},
            "escalation": {
                "warning_before_seconds": float(
                    mission.get("escalation_warning_seconds", 900.0)
                ),
                "critical_before_seconds": float(
                    mission.get("escalation_critical_seconds", 300.0)
                ),
            },
            "budget": {
                "max_tasks": int(mission.get("max_tasks", 256)),
                "max_retries": int(mission.get("max_retries", 8)),
            },
            "cancellation": {
                "mode": str(mission.get("cancellation_mode", "graceful")),
                "operator_only": True,
            },
        }

    def _backfill_policy_revisions(self) -> None:
        rows = self.db.execute(
            "SELECT * FROM missions ORDER BY created_at ASC"
        ).fetchall()
        defaults = self._default_policy_config()
        for row in rows:
            mission = self._row(row)
            existing = self.db.execute(
                "SELECT revision, policy_hash "
                "FROM mission_policy_revisions WHERE mission_id=? "
                "ORDER BY revision DESC LIMIT 1",
                (mission["id"],),
            ).fetchone()
            if existing:
                continue
            policy = self._policy_document(mission, defaults)
            policy_hash = hashlib.sha256(
                json.dumps(
                    policy,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            created_at = mission["created_at"] or now_iso()
            self.db.execute(
                "INSERT OR IGNORE INTO mission_policy_revisions "
                "(mission_id,revision,policy_json,policy_hash,actor,reason,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    mission["id"],
                    1,
                    json.dumps(policy, ensure_ascii=False),
                    policy_hash,
                    "migration",
                    "initial_migration",
                    created_at,
                ),
            )
            self.db.execute(
                "UPDATE missions SET policy_revision=1, policy_hash=?, "
                "approval_external=?, approval_financial=?, cancellation_mode=? "
                "WHERE id=?",
                (
                    policy_hash,
                    int(policy["approval"]["external_actions_require_approval"]),
                    int(policy["approval"]["financial_actions_require_approval"]),
                    policy["cancellation"]["mode"],
                    mission["id"],
                ),
            )
        self.db.commit()

    def _record_policy_revision(
        self,
        mission_id: str,
        actor: str = "system",
        reason: str = "policy_mutation",
    ) -> dict[str, Any] | None:
        mission = self.get(mission_id)
        if mission is None:
            return None
        current = self.db.execute(
            "SELECT COALESCE(MAX(revision), 0) AS revision "
            "FROM mission_policy_revisions WHERE mission_id=?",
            (mission_id,),
        ).fetchone()
        revision = int(current["revision"] or 0) + 1
        policy = self._policy_document(mission)
        policy_hash = hashlib.sha256(
            json.dumps(
                policy,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        created_at = now_iso()
        self.db.execute(
            "INSERT INTO mission_policy_revisions "
            "(mission_id,revision,policy_json,policy_hash,actor,reason,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                mission_id,
                revision,
                json.dumps(policy, ensure_ascii=False),
                policy_hash,
                str(actor),
                str(reason),
                created_at,
            ),
        )
        self.db.execute(
            "UPDATE missions SET policy_revision=?, policy_hash=?, updated_at=? WHERE id=?",
            (revision, policy_hash, created_at, mission_id),
        )
        self.db.commit()
        self.add_timeline_event(
            mission_id,
            "mission.policy_revision_created",
            {"revision": revision, "policy_hash": policy_hash, "reason": reason},
            status=mission["status"],
            created_at=created_at,
        )
        return self.policy_for_mission(mission_id)

    def policy_for_mission(self, mission_id: str) -> dict[str, Any] | None:
        mission = self.get(mission_id)
        if mission is None:
            return None
        row = self.db.execute(
            "SELECT * FROM mission_policy_revisions "
            "WHERE mission_id=? AND revision=?",
            (mission_id, int(mission.get("policy_revision", 1))),
        ).fetchone()
        if row is None:
            self._backfill_policy_revisions()
            row = self.db.execute(
                "SELECT * FROM mission_policy_revisions "
                "WHERE mission_id=? ORDER BY revision DESC LIMIT 1",
                (mission_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "mission_id": mission_id,
            "revision": int(row["revision"]),
            "hash": row["policy_hash"],
            "policy": json.loads(row["policy_json"] or "{}"),
            "actor": row["actor"],
            "reason": row["reason"],
            "created_at": row["created_at"],
        }

    def policy_revisions_for_mission(
        self,
        mission_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        rows = self.db.execute(
            "SELECT * FROM mission_policy_revisions "
            "WHERE mission_id=? ORDER BY revision DESC LIMIT ?",
            (mission_id, limit),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "mission_id": row["mission_id"],
                "revision": int(row["revision"]),
                "hash": row["policy_hash"],
                "policy": json.loads(row["policy_json"] or "{}"),
                "actor": row["actor"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]

    def set_policy(
        self,
        mission_id: str,
        external_actions_require_approval: bool | None = None,
        financial_actions_require_approval: bool | None = None,
        cancellation_mode: str | None = None,
        actor: str = "operator",
        reason: str = "operator_policy_update",
    ) -> dict[str, Any] | None:
        mission = self.get(mission_id)
        if mission is None:
            return None
        current = self.policy_for_mission(mission_id)
        approval = dict(
            (current or {}).get("policy", {}).get("approval", {})
        )
        if external_actions_require_approval is not None:
            approval["external_actions_require_approval"] = bool(
                external_actions_require_approval
            )
        if financial_actions_require_approval is not None:
            approval["financial_actions_require_approval"] = bool(
                financial_actions_require_approval
            )
        mode = cancellation_mode or mission.get("cancellation_mode", "graceful")
        if mode not in {"graceful"}:
            raise ValueError("cancellation_mode must be 'graceful'")
        self.db.execute(
            "UPDATE missions SET approval_external=?, approval_financial=?, "
            "cancellation_mode=? WHERE id=?",
            (
                int(approval.get("external_actions_require_approval", True)),
                int(approval.get("financial_actions_require_approval", True)),
                mode,
                mission_id,
            ),
        )
        self.db.commit()
        revision = self._record_policy_revision(
            mission_id,
            actor=actor,
            reason=reason,
        )
        self.add_audit_event(
            mission_id,
            "mission.policy.changed",
            actor=actor,
            payload={
                "external_actions_require_approval": bool(approval.get("external_actions_require_approval", True)),
                "financial_actions_require_approval": bool(approval.get("financial_actions_require_approval", True)),
                "cancellation_mode": mode,
                "reason": reason,
                "revision": revision.get("revision") if revision else None,
            },
        )
        return revision

    def integrity_for_mission(
        self,
        mission_id: str,
        task_db: str | Path,
    ) -> dict[str, Any] | None:
        mission = self.get(mission_id)
        if mission is None:
            return None
        graph = self.graph_for_mission(mission_id, task_db)
        counts = dict(graph.get("counts") or {})
        violations: list[dict[str, Any]] = []
        task_count = int(counts.get("total", 0))
        aggregate = self._aggregate_task_graph(
            mission["root_task_ids"],
            str(task_db),
            fallback=mission["status"],
        ) if task_count else mission["status"]
        if task_count and aggregate != mission["status"]:
            violations.append({
                "code": "mission_status_mismatch",
                "mission_status": mission["status"],
                "graph_status": aggregate,
            })
        active = (
            int(counts.get("queued", 0))
            + int(counts.get("running", 0))
            + int(counts.get("blocked", 0))
        )
        if mission["status"] in TERMINAL and active:
            violations.append({
                "code": "terminal_with_active_tasks",
                "status": mission["status"],
                "active": active,
            })
        if mission["status"] in TERMINAL and not mission.get("completed_at"):
            violations.append({"code": "terminal_without_completed_at"})
        if mission["status"] not in TERMINAL and mission.get("completed_at"):
            violations.append({"code": "active_with_completed_at"})
        roots = list(mission.get("root_task_ids") or [])
        graph_ids = {str(node["id"]) for node in graph.get("nodes", [])}
        missing_roots = [root for root in roots if str(root) not in graph_ids]
        if missing_roots:
            violations.append({
                "code": "missing_root_tasks",
                "task_ids": missing_roots,
            })
        latest_task_id = mission.get("latest_task_id")
        if latest_task_id and str(latest_task_id) not in graph_ids:
            violations.append({
                "code": "latest_task_missing_from_graph",
                "task_id": latest_task_id,
            })

        budget = self.budget_for_mission(mission_id, task_db)
        if budget and mission.get("budget_status") != budget["status"]:
            violations.append({
                "code": "budget_status_mismatch",
                "mission_status": mission.get("budget_status"),
                "computed_status": budget["status"],
            })

        policy = self.policy_for_mission(mission_id)
        if policy:
            if int(mission.get("policy_revision", 1)) != int(policy["revision"]):
                violations.append({
                    "code": "policy_revision_mismatch",
                    "mission_revision": mission.get("policy_revision"),
                    "stored_revision": policy["revision"],
                })
            if mission.get("policy_hash") != policy["hash"]:
                violations.append({
                    "code": "policy_hash_mismatch",
                    "mission_hash": mission.get("policy_hash"),
                    "stored_hash": policy["hash"],
                })

        audit_integrity = self.verify_audit_chain(mission_id)
        if not audit_integrity["valid"]:
            violations.append({
                "code": "audit_chain_invalid",
                "detail": audit_integrity,
            })

        status = "violated" if violations else "healthy"
        checked_at = now_iso()
        fingerprint = hashlib.sha256(
            json.dumps(
                violations,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        return {
            "mission_id": mission_id,
            "status": status,
            "checked_at": checked_at,
            "violations": violations,
            "fingerprint": fingerprint,
            "task_count": task_count,
            "active_task_count": active,
            "graph_status": aggregate,
            "budget": budget,
            "policy_revision": policy["revision"] if policy else None,
            "policy_hash": policy["hash"] if policy else None,
            "audit_integrity": audit_integrity,
        }

    def check_integrity(
        self,
        mission_id: str,
        task_db: str | Path,
    ) -> dict[str, Any] | None:
        report = self.integrity_for_mission(mission_id, task_db)
        if report is None:
            return None
        previous = self.db.execute(
            "SELECT fingerprint FROM mission_integrity_checks "
            "WHERE mission_id=? ORDER BY id DESC LIMIT 1",
            (mission_id,),
        ).fetchone()
        previous_fingerprint = previous["fingerprint"] if previous else None
        self.db.execute(
            "INSERT INTO mission_integrity_checks "
            "(mission_id,status,checked_at,violations_json,fingerprint) "
            "VALUES(?,?,?,?,?)",
            (
                mission_id,
                report["status"],
                report["checked_at"],
                json.dumps(report["violations"], ensure_ascii=False),
                report["fingerprint"],
            ),
        )
        self.db.commit()
        if report["violations"] and report["fingerprint"] != previous_fingerprint:
            summary = "; ".join(
                str(item.get("code", "unknown"))
                for item in report["violations"]
            )
            self.add_timeline_event(
                mission_id,
                "mission.integrity_violation",
                {
                    "summary": summary,
                    "violations": report["violations"],
                    "fingerprint": report["fingerprint"],
                },
                status=report["status"],
                created_at=report["checked_at"],
            )
        return report

    def check_integrity_all(
        self,
        task_db: str | Path,
    ) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT id FROM missions ORDER BY updated_at ASC"
        ).fetchall()
        healthy = 0
        violated = 0
        for row in rows:
            report = self.check_integrity(row["id"], task_db)
            if not report:
                continue
            if report["status"] == "violated":
                violated += 1
            else:
                healthy += 1
        return {
            "checked": healthy + violated,
            "healthy": healthy,
            "violated": violated,
        }

    def integrity_history(
        self,
        mission_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        rows = self.db.execute(
            "SELECT * FROM mission_integrity_checks "
            "WHERE mission_id=? ORDER BY id DESC LIMIT ?",
            (mission_id, limit),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "mission_id": row["mission_id"],
                "status": row["status"],
                "checked_at": row["checked_at"],
                "violations": json.loads(row["violations_json"] or "[]"),
                "fingerprint": row["fingerprint"],
            }
            for row in reversed(rows)
        ]

    def add_audit_event(
        self,
        mission_id: str,
        action: str,
        actor: str = "operator",
        result: str = "success",
        payload: dict[str, Any] | None = None,
        task_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """Append one tamper-evident operator/system decision record."""
        event_time = created_at or now_iso()
        normalized_payload = dict(payload or {})
        mission_row = self.db.execute(
            "SELECT policy_revision, policy_hash FROM missions WHERE id=?",
            (mission_id,),
        ).fetchone()
        if mission_row:
            normalized_payload.setdefault("policy_revision", mission_row["policy_revision"])
            normalized_payload.setdefault("policy_hash", mission_row["policy_hash"])
        previous = self.db.execute(
            "SELECT entry_hash FROM mission_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_hash = previous["entry_hash"] if previous else ""
        canonical = json.dumps(
            {
                "mission_id": mission_id,
                "task_id": task_id,
                "actor": actor,
                "action": action,
                "result": result,
                "payload": normalized_payload,
                "created_at": event_time,
                "prev_hash": prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.db.execute(
            """
            INSERT INTO mission_audit
            (mission_id,task_id,actor,action,result,payload,created_at,prev_hash,entry_hash)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                mission_id,
                task_id,
                str(actor or "operator"),
                str(action),
                str(result),
                json.dumps(normalized_payload, ensure_ascii=False),
                event_time,
                prev_hash or None,
                entry_hash,
            ),
        )
        self.db.commit()
        row = self.db.execute(
            "SELECT * FROM mission_audit WHERE entry_hash=?",
            (entry_hash,),
        ).fetchone()
        return self._audit_row(row)

    def audit_for_mission(
        self,
        mission_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        rows = self.db.execute(
            "SELECT * FROM mission_audit WHERE mission_id=? ORDER BY id DESC LIMIT ?",
            (mission_id, limit),
        ).fetchall()
        return [self._audit_row(row) for row in reversed(rows)]

    def list_audit(
        self,
        limit: int = 100,
        mission_id: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if mission_id:
            return self.audit_for_mission(mission_id, limit)
        rows = self.db.execute(
            "SELECT * FROM mission_audit ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._audit_row(row) for row in reversed(rows)]

    def verify_audit_chain(self, mission_id: str | None = None) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT * FROM mission_audit ORDER BY id ASC"
        ).fetchall()
        previous_global = ""
        checked = 0
        for row in rows:
            if mission_id and row["mission_id"] != mission_id:
                previous_global = row["entry_hash"]
                continue
            expected_prev = previous_global or None
            canonical = json.dumps(
                {
                    "mission_id": row["mission_id"],
                    "task_id": row["task_id"],
                    "actor": row["actor"],
                    "action": row["action"],
                    "result": row["result"],
                    "payload": json.loads(row["payload"] or "{}"),
                    "created_at": row["created_at"],
                    "prev_hash": row["prev_hash"] or "",
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if (row["prev_hash"] or None) != expected_prev or row["entry_hash"] != expected_hash:
                return {
                    "valid": False,
                    "checked": checked,
                    "broken_id": int(row["id"]),
                    "reason": "hash_chain_mismatch",
                }
            previous_global = row["entry_hash"]
            checked += 1
        return {"valid": True, "checked": checked}

    def add_timeline_event(
        self,
        mission_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        task_id: str | None = None,
        status: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        event_time = created_at or now_iso()
        self.db.execute(
            """
            INSERT INTO mission_timeline
            (mission_id, task_id, kind, status, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mission_id,
                task_id,
                kind,
                status,
                json.dumps(payload or {}, ensure_ascii=False),
                event_time,
            ),
        )
        self.db.commit()
        row = self.db.execute(
            "SELECT id, mission_id, task_id, kind, status, payload, created_at "
            "FROM mission_timeline WHERE rowid=last_insert_rowid()"
        ).fetchone()
        event = self._timeline_row(row)
        self._create_attention_from_event(event)
        return event

    def _create_attention_from_event(self, event: dict[str, Any]) -> None:
        spec = self._attention_spec(event)
        if spec is None:
            return
        dedupe_key = f"{event['mission_id']}|timeline:{event.get('id')}"
        self.db.execute(
            """
            INSERT OR IGNORE INTO mission_attention
            (mission_id,task_id,severity,kind,title,detail,status,created_at,dedupe_key)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                event["mission_id"],
                event.get("task_id"),
                spec["severity"],
                event["kind"],
                spec["title"],
                spec["detail"],
                "open",
                event["created_at"],
                dedupe_key,
            ),
        )
        self.db.commit()

    @staticmethod
    def _attention_spec(event: dict[str, Any]) -> dict[str, str] | None:
        kind = str(event.get("kind") or "")
        payload = event.get("payload") or {}
        if kind == "mission.escalation_warning":
            seconds = payload.get("seconds_to_deadline")
            return {
                "severity": "warning",
                "title": "Mission approaching deadline",
                "detail": f"About {max(0.0, float(seconds or 0.0)):.0f}s remain before the deadline.",
            }
        if kind == "mission.escalation_critical":
            seconds = payload.get("seconds_to_deadline")
            return {
                "severity": "critical",
                "title": "Mission deadline is critical",
                "detail": f"About {max(0.0, float(seconds or 0.0)):.0f}s remain before the deadline.",
            }
        if kind == "mission.deadline_exceeded":
            return {
                "severity": "critical",
                "title": "Mission deadline exceeded",
                "detail": f"Deadline {payload.get('deadline_at') or 'unknown'} has passed.",
            }
        if kind == "task.approval_required":
            return {
                "severity": "critical",
                "title": "Task requires approval",
                "detail": str(payload.get("reason") or "Operator approval is required."),
            }
        if kind == "task.escalation_required":
            return {
                "severity": "critical",
                "title": "Task requires operator attention",
                "detail": str(payload.get("reason") or "Task execution requires attention."),
            }
        if kind == "mission.integrity_violation":
            return {
                "severity": "critical",
                "title": "Mission state integrity violation",
                "detail": str(payload.get("summary") or "Mission state invariants failed; operator review required."),
            }
        if kind == "mission.budget_exhausted":
            return {
                "severity": "critical",
                "title": "Mission execution budget exhausted",
                "detail": (
                    f"Task limit {payload.get('task_count', 0)}/{payload.get('max_tasks', 0)}; "
                    f"retry limit {payload.get('retry_count', 0)}/{payload.get('max_retries', 0)}."
                ),
            }
        if kind == "mission.cancel_requested":
            return {
                "severity": "warning",
                "title": "Mission cancellation requested",
                "detail": "Running task cancellation was requested and will complete gracefully.",
            }
        if kind == "task.cancel_requested":
            return {
                "severity": "warning",
                "title": "Task cancellation requested",
                "detail": "The running task received a graceful cancellation request.",
            }
        if kind == "mission.task_updated" and event.get("status") == "failed":
            return {
                "severity": "critical",
                "title": "Mission task failed",
                "detail": str(payload.get("outcome", {}).get("error") or "A mission task failed."),
            }
        if kind == "mission.task_updated" and event.get("status") == "blocked":
            return {
                "severity": "critical",
                "title": "Mission task blocked",
                "detail": str(payload.get("outcome", {}).get("error") or "A mission task is blocked."),
            }
        return None

    def attention_for_mission(
        self,
        mission_id: str,
        limit: int = 50,
        include_acknowledged: bool = False,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        query = (
            "SELECT * FROM mission_attention WHERE mission_id=? "
            + ("" if include_acknowledged else "AND status='open' ")
            + "ORDER BY id DESC LIMIT ?"
        )
        rows = self.db.execute(query, (mission_id, limit)).fetchall()
        return [self._attention_row(row) for row in reversed(rows)]

    def list_attention(
        self,
        limit: int = 100,
        mission_id: str | None = None,
        include_acknowledged: bool = False,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        clauses = []
        params: list[Any] = []
        if mission_id:
            clauses.append("mission_id=?")
            params.append(mission_id)
        if not include_acknowledged:
            clauses.append("status='open'")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.db.execute(
            "SELECT * FROM mission_attention" + where + " ORDER BY id DESC LIMIT ?",
            tuple(params) + (limit,),
        ).fetchall()
        return [self._attention_row(row) for row in reversed(rows)]

    def acknowledge_attention(
        self,
        attention_id: int,
        acknowledged_by: str = "operator",
    ) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM mission_attention WHERE id=?",
            (int(attention_id),),
        ).fetchone()
        if row is None:
            return {"status": "missing", "attention_id": int(attention_id)}
        if row["status"] == "acknowledged":
            return self._attention_row(row)
        acknowledged_at = now_iso()
        self.db.execute(
            """
            UPDATE mission_attention
            SET status='acknowledged', acknowledged_at=?, acknowledged_by=?
            WHERE id=?
            """,
            (acknowledged_at, acknowledged_by, int(attention_id)),
        )
        self.db.commit()
        result = self._attention_row(
            self.db.execute(
                "SELECT * FROM mission_attention WHERE id=?",
                (int(attention_id),),
            ).fetchone()
        )
        self.add_audit_event(
            result["mission_id"],
            "attention.acknowledge",
            actor=acknowledged_by,
            payload={"attention_id": int(attention_id), "status": result["status"]},
            task_id=result.get("task_id"),
        )
        return result

    @staticmethod
    def _attention_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "mission_id": row["mission_id"],
            "task_id": row["task_id"],
            "severity": row["severity"],
            "kind": row["kind"],
            "title": row["title"],
            "detail": row["detail"],
            "status": row["status"],
            "created_at": row["created_at"],
            "acknowledged_at": row["acknowledged_at"],
            "acknowledged_by": row["acknowledged_by"],
        }

    @staticmethod
    def _audit_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "mission_id": row["mission_id"],
            "task_id": row["task_id"],
            "actor": row["actor"],
            "action": row["action"],
            "result": row["result"],
            "payload": json.loads(row["payload"] or "{}"),
            "created_at": row["created_at"],
            "prev_hash": row["prev_hash"],
            "entry_hash": row["entry_hash"],
        }

    def timeline_for_mission(
        self,
        mission_id: str,
        limit: int = 200,
        task_db: str | Path | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        events = self.db.execute(
            """
            SELECT id, mission_id, task_id, kind, status, payload, created_at
            FROM mission_timeline
            WHERE mission_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (mission_id, limit),
        ).fetchall()
        items = [self._timeline_row(row) for row in reversed(events)]
        if task_db:
            mission = self.get(mission_id)
            if mission:
                graph = self.graph_for_mission(mission_id, task_db)
                task_ids = [str(node["id"]) for node in graph.get("nodes", [])]
                if task_ids:
                    path = Path(task_db)
                    if path.exists():
                        try:
                            conn = sqlite3.connect(path)
                            conn.row_factory = sqlite3.Row
                            placeholders = ",".join("?" for _ in task_ids)
                            rows = conn.execute(
                                "SELECT task_id, kind, payload, created_at "
                                "FROM events WHERE task_id IN (%s) "
                                "ORDER BY rowid DESC LIMIT ?" % placeholders,
                                tuple(task_ids) + (limit,),
                            ).fetchall()
                            conn.close()
                            for row in rows:
                                payload = {}
                                try:
                                    payload = json.loads(row["payload"] or "{}")
                                except (TypeError, ValueError):
                                    payload = {"raw": row["payload"]}
                                items.append({
                                    "id": None,
                                    "mission_id": mission_id,
                                    "task_id": row["task_id"],
                                    "kind": str(row["kind"]),
                                    "status": None,
                                    "payload": payload,
                                    "created_at": row["created_at"],
                                    "source": "task_event",
                                })
                        except sqlite3.Error:
                            pass
        items.sort(key=lambda item: (str(item.get("created_at") or ""), int(item.get("id") or 0)))
        return items[-limit:]


    def replay_for_mission(
        self,
        mission_id: str,
        task_db: str | Path,
        limit: int = 500,
    ) -> dict[str, Any] | None:
        """Build a deterministic, read-only forensic replay from durable evidence."""
        mission = self.get(mission_id)
        if mission is None:
            return None

        limit = max(1, min(int(limit), 1000))
        graph = self.graph_for_mission(mission_id, task_db)
        timeline = self.timeline_for_mission(
            mission_id,
            limit=limit,
            task_db=task_db,
        )
        audit = self.audit_for_mission(mission_id, limit=limit)
        integrity = self.verify_audit_chain(mission_id)
        policy_revisions = self.policy_revisions_for_mission(mission_id, limit=limit)

        replay: list[dict[str, Any]] = []
        for item in timeline:
            replay.append({
                "source": item.get("source", "mission"),
                "id": item.get("id"),
                "mission_id": mission_id,
                "task_id": item.get("task_id"),
                "kind": item.get("kind"),
                "status": item.get("status"),
                "payload": item.get("payload") or {},
                "created_at": item.get("created_at"),
            })
        for item in policy_revisions:
            replay.append({
                "source": "policy",
                "id": item.get("id"),
                "mission_id": mission_id,
                "task_id": None,
                "kind": "policy.revision",
                "status": "active" if item.get("revision") == mission.get("policy_revision") else "historical",
                "payload": {
                    "revision": item.get("revision"),
                    "hash": item.get("hash"),
                    "actor": item.get("actor"),
                    "reason": item.get("reason"),
                    "policy": item.get("policy") or {},
                },
                "created_at": item.get("created_at"),
            })
        for item in audit:
            replay.append({
                "source": "audit",
                "id": item.get("id"),
                "mission_id": mission_id,
                "task_id": item.get("task_id"),
                "kind": f"audit.{item.get('action')}",
                "status": item.get("result"),
                "payload": {
                    "actor": item.get("actor"),
                    "result": item.get("result"),
                    **(item.get("payload") or {}),
                },
                "created_at": item.get("created_at"),
            })

        replay.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                0 if item.get("source") == "mission" else 1,
                int(item.get("id") or 0),
            )
        )
        replay = replay[-limit:]

        first_seen = replay[0]["created_at"] if replay else mission.get("created_at")
        last_seen = replay[-1]["created_at"] if replay else mission.get("updated_at")
        duration_seconds = None
        if first_seen and last_seen:
            try:
                start = datetime.fromisoformat(str(first_seen).replace("Z", "+00:00"))
                end = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
                duration_seconds = max(0.0, (end - start).total_seconds())
            except ValueError:
                duration_seconds = None

        by_source: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for item in replay:
            source = str(item.get("source") or "unknown")
            kind = str(item.get("kind") or "unknown")
            by_source[source] = by_source.get(source, 0) + 1
            by_kind[kind] = by_kind.get(kind, 0) + 1

        return {
            "mission_id": mission_id,
            "mission": mission,
            "graph": graph,
            "audit_integrity": integrity,
            "policy": self.policy_for_mission(mission_id),
            "policy_revisions": policy_revisions,
            "audit_count": len(audit),
            "timeline_count": len(timeline),
            "policy_revision_count": len(policy_revisions),
            "replay_count": len(replay),
            "summary": {
                "first_event_at": first_seen,
                "last_event_at": last_seen,
                "duration_seconds": duration_seconds,
                "by_source": by_source,
                "top_kinds": sorted(
                    by_kind.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:20],
            },
            "replay": [
                {**item, "sequence": index + 1}
                for index, item in enumerate(replay)
            ],
        }

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
             latest_task_id,latest_outcome,created_at,updated_at,completed_at,
             deadline_at,watchdog_status,watchdog_checked_at,
             escalation_level,escalation_warning_seconds,escalation_critical_seconds,
             escalation_checked_at,max_tasks,max_retries,budget_status,budget_checked_at,
             policy_revision,policy_hash,approval_external,approval_financial,cancellation_mode)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                None,
                "ok",
                now,
                "normal",
                900.0,
                300.0,
                now,
                256,
                8,
                "ok",
                now,
                1,
                None,
                int(bool(self._default_policy_config().get("external_actions_require_approval", True))),
                int(bool(self._default_policy_config().get("financial_actions_require_approval", True))),
                "graceful",
            ),
        )
        self.db.commit()
        self.add_timeline_event(
            mission_id,
            "mission.created",
            {"goal": goal, "strategy": strategy},
            status="queued",
            created_at=now,
        )
        self.add_audit_event(
            mission_id,
            "mission.created",
            actor="system",
            payload={"goal": goal, "strategy": strategy},
            created_at=now,
        )
        self._record_policy_revision(mission_id, actor="system", reason="mission_created")
        return self.get(mission_id) or {}

    def budget_for_mission(
        self,
        mission_id: str,
        task_db: str | Path,
    ) -> dict[str, Any] | None:
        mission = self.get(mission_id)
        if mission is None:
            return None
        graph = self.graph_for_mission(mission_id, task_db)
        task_count = len(graph.get("nodes", []))
        task_limit = max(1, int(mission.get("max_tasks", 256)))
        task_retry_count = 0
        path = Path(task_db)
        if path.exists():
            try:
                conn = sqlite3.connect(path)
                graph_task_ids = [str(node["id"]) for node in graph.get("nodes", [])]
                if graph_task_ids:
                    placeholders = ",".join("?" for _ in graph_task_ids)
                    row = conn.execute(
                        "SELECT COUNT(*) AS count FROM events "
                        "WHERE kind='task.retry_scheduled' AND task_id IN (%s)" % placeholders,
                        tuple(graph_task_ids),
                    ).fetchone()
                    task_retry_count = int(row[0] or 0)
                conn.close()
            except sqlite3.Error:
                task_retry_count = 0
        retry_limit = max(0, int(mission.get("max_retries", 8)))
        tasks_exhausted = task_count >= task_limit
        retries_exhausted = task_retry_count >= retry_limit if retry_limit >= 0 else False
        if tasks_exhausted and retries_exhausted:
            status = "tasks_and_retries_exhausted"
        elif tasks_exhausted:
            status = "tasks_exhausted"
        elif retries_exhausted:
            status = "retries_exhausted"
        else:
            status = "ok"
        return {
            "status": status,
            "task_count": task_count,
            "max_tasks": task_limit,
            "retry_count": task_retry_count,
            "max_retries": retry_limit,
            "remaining_tasks": max(0, task_limit - task_count),
            "remaining_retries": max(0, retry_limit - task_retry_count),
            "checked_at": now_iso(),
        }

    def can_create_task(
        self,
        mission_id: str,
        task_db: str | Path,
    ) -> dict[str, Any]:
        budget = self.budget_for_mission(mission_id, task_db)
        if budget is None:
            return {"allowed": False, "reason": "mission_missing", "mission_id": mission_id}
        if budget["task_count"] >= budget["max_tasks"]:
            return {"allowed": False, "reason": "max_tasks_exhausted", **budget}
        return {"allowed": True, **budget}

    def can_retry_task(
        self,
        mission_id: str,
        task_db: str | Path,
    ) -> dict[str, Any]:
        budget = self.budget_for_mission(mission_id, task_db)
        if budget is None:
            return {"allowed": False, "reason": "mission_missing", "mission_id": mission_id}
        if budget["retry_count"] >= budget["max_retries"]:
            return {"allowed": False, "reason": "max_retries_exhausted", **budget}
        return {"allowed": True, **budget}

    def set_budget(
        self,
        mission_id: str,
        max_tasks: int | None = None,
        max_retries: int | None = None,
        actor: str = "operator",
        task_db: str | Path | None = None,
    ) -> dict[str, Any]:
        mission = self.get(mission_id)
        if mission is None:
            return {"status": "missing", "mission_id": mission_id}
        tasks_limit = mission.get("max_tasks", 256) if max_tasks is None else int(max_tasks)
        retries_limit = mission.get("max_retries", 8) if max_retries is None else int(max_retries)
        if tasks_limit < 1:
            raise ValueError("max_tasks must be >= 1")
        if retries_limit < 0:
            raise ValueError("max_retries must be >= 0")
        now = now_iso()
        self.db.execute(
            "UPDATE missions SET max_tasks=?, max_retries=?, budget_status='ok', budget_checked_at=?, updated_at=? WHERE id=?",
            (tasks_limit, retries_limit, now, now, mission_id),
        )
        self.db.commit()
        self.add_timeline_event(
            mission_id,
            "mission.budget_policy_set",
            {"max_tasks": tasks_limit, "max_retries": retries_limit},
            status=mission["status"],
            created_at=now,
        )
        self.add_audit_event(
            mission_id,
            "mission.budget.policy_set",
            actor=actor,
            payload={"max_tasks": tasks_limit, "max_retries": retries_limit},
        )
        if task_db is not None:
            self.update_budget_status(mission_id, task_db)
        self._record_policy_revision(mission_id, actor=actor, reason="budget_policy_changed")
        return self.get(mission_id) or {}

    def update_budget_status(
        self,
        mission_id: str,
        task_db: str | Path,
    ) -> dict[str, Any] | None:
        budget = self.budget_for_mission(mission_id, task_db)
        if budget is None:
            return None
        now = now_iso()
        previous = self.get(mission_id) or {}
        previous_status = previous.get("budget_status", "ok")
        if budget["status"] != previous_status:
            self.db.execute(
                "UPDATE missions SET budget_status=?, budget_checked_at=?, updated_at=? WHERE id=?",
                (budget["status"], now, now, mission_id),
            )
        else:
            self.db.execute(
                "UPDATE missions SET budget_checked_at=? WHERE id=?",
                (now, mission_id),
            )
        self.db.commit()
        if budget["status"] != previous_status and budget["status"] != "ok":
            self.add_timeline_event(
                mission_id,
                "mission.budget_exhausted",
                budget,
                status=previous.get("status"),
                created_at=now,
            )
        return budget

    def set_deadline(
        self,
        mission_id: str,
        deadline_at: str | None,
        actor: str = "operator",
        now: str | None = None,
    ) -> dict[str, Any]:
        mission = self.get(mission_id)
        if mission is None:
            return {"status": "missing", "mission_id": mission_id}
        normalized = None
        if deadline_at:
            try:
                parsed = datetime.fromisoformat(
                    str(deadline_at).replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ValueError("deadline_at must be an ISO-8601 timestamp") from exc
            if parsed.tzinfo is None:
                raise ValueError("deadline_at must include a timezone offset")
            normalized = parsed.astimezone(timezone.utc).isoformat()

        effective_now = now or now_iso()
        self.db.execute(
            """
            UPDATE missions
            SET deadline_at=?, watchdog_status=?, watchdog_checked_at=?,
                escalation_level=?, escalation_checked_at=?, updated_at=?
            WHERE id=?
            """,
            (normalized, "ok", effective_now, "normal", effective_now, effective_now, mission_id),
        )
        self.db.commit()
        self.add_timeline_event(
            mission_id,
            "mission.deadline_cleared" if normalized is None else "mission.deadline_set",
            {"deadline_at": normalized},
            status=mission["status"],
            created_at=effective_now,
        )
        self.watchdog_for_mission(mission_id, task_db=None, now=effective_now)
        result = self.get(mission_id) or {}
        self.add_audit_event(
            mission_id,
            "mission.deadline.clear" if normalized is None else "mission.deadline.set",
            actor=actor,
            payload={"deadline_at": normalized},
            result="success",
        )
        self._record_policy_revision(mission_id, actor=actor, reason="deadline_changed")
        return result

    def set_escalation_policy(
        self,
        mission_id: str,
        warning_before_seconds: float = 900.0,
        critical_before_seconds: float = 300.0,
        actor: str = "operator",
    ) -> dict[str, Any]:
        mission = self.get(mission_id)
        if mission is None:
            return {"status": "missing", "mission_id": mission_id}
        try:
            warning = float(warning_before_seconds)
            critical = float(critical_before_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("escalation thresholds must be numeric seconds") from exc
        if warning < 0 or critical < 0:
            raise ValueError("escalation thresholds must be non-negative")
        if warning < critical:
            raise ValueError("warning_before_seconds must be >= critical_before_seconds")
        now = now_iso()
        self.db.execute(
            """
            UPDATE missions
            SET escalation_warning_seconds=?,
                escalation_critical_seconds=?,
                escalation_checked_at=?,
                updated_at=?
            WHERE id=?
            """,
            (warning, critical, now, now, mission_id),
        )
        self.db.commit()
        self.add_timeline_event(
            mission_id,
            "mission.escalation_policy_set",
            {
                "warning_before_seconds": warning,
                "critical_before_seconds": critical,
            },
            status=mission["status"],
            created_at=now,
        )
        self.watchdog_for_mission(mission_id, task_db=None, now=now)
        result = self.get(mission_id) or {}
        self.add_audit_event(
            mission_id,
            "mission.escalation.policy_set",
            actor=actor,
            payload={
                "warning_before_seconds": warning,
                "critical_before_seconds": critical,
            },
            result="success",
        )
        self._record_policy_revision(mission_id, actor=actor, reason="escalation_policy_changed")
        return result

    def watchdog_for_mission(
        self,
        mission_id: str,
        task_db: str | Path | None,
        now: str | None = None,
    ) -> dict[str, Any] | None:
        mission = self.get(mission_id)
        if mission is None:
            return None
        if not mission.get("deadline_at") or mission.get("status") in TERMINAL:
            return mission
        current = datetime.fromisoformat(
            str(now or now_iso()).replace("Z", "+00:00")
        )
        deadline = datetime.fromisoformat(
            str(mission["deadline_at"]).replace("Z", "+00:00")
        )
        if current.tzinfo is None or deadline.tzinfo is None:
            return mission

        checked_at = current.astimezone(timezone.utc).isoformat()
        seconds_to_deadline = (deadline - current).total_seconds()
        warning_before = float(mission.get("escalation_warning_seconds") or 900.0)
        critical_before = float(mission.get("escalation_critical_seconds") or 300.0)
        overdue = seconds_to_deadline <= 0
        watchdog_status = "overdue" if overdue else "ok"
        if overdue:
            escalation_level = "overdue"
        elif seconds_to_deadline <= critical_before:
            escalation_level = "critical"
        elif seconds_to_deadline <= warning_before:
            escalation_level = "warning"
        else:
            escalation_level = "normal"

        previous_watchdog = mission.get("watchdog_status", "ok")
        previous_level = mission.get("escalation_level", "normal")
        changed = (
            previous_watchdog != watchdog_status
            or previous_level != escalation_level
        )
        outcome = dict(mission.get("latest_outcome") or {})
        if overdue:
            outcome["deadline_exceeded"] = mission["deadline_at"]
        else:
            outcome.pop("deadline_exceeded", None)
        outcome["deadline_escalation"] = {
            "level": escalation_level,
            "seconds_to_deadline": round(seconds_to_deadline, 3),
            "warning_before_seconds": warning_before,
            "critical_before_seconds": critical_before,
        }

        self.db.execute(
            """
            UPDATE missions
            SET watchdog_status=?, watchdog_checked_at=?,
                escalation_level=?, escalation_checked_at=?,
                latest_outcome=?, updated_at=?
            WHERE id=?
            """,
            (
                watchdog_status,
                checked_at,
                escalation_level,
                checked_at,
                json.dumps(outcome, ensure_ascii=False),
                checked_at,
                mission_id,
            ),
        )
        self.db.commit()

        if changed:
            if escalation_level == "warning":
                kind = "mission.escalation_warning"
            elif escalation_level == "critical":
                kind = "mission.escalation_critical"
            elif escalation_level == "overdue":
                kind = "mission.deadline_exceeded"
            else:
                kind = "mission.escalation_cleared"
            self.add_timeline_event(
                mission_id,
                kind,
                {
                    "deadline_at": mission["deadline_at"],
                    "seconds_to_deadline": round(seconds_to_deadline, 3),
                    "watchdog_status": watchdog_status,
                    "escalation_level": escalation_level,
                    "warning_before_seconds": warning_before,
                    "critical_before_seconds": critical_before,
                },
                status=mission["status"],
                created_at=checked_at,
            )
        return self.get(mission_id) or mission

    def watchdog(
        self,
        task_db: str | Path,
        now: str | None = None,
    ) -> dict[str, int]:
        rows = self.db.execute(
            """
            SELECT id FROM missions
            WHERE deadline_at IS NOT NULL
              AND status IN ('queued','running','blocked')
            ORDER BY updated_at ASC
            """
        ).fetchall()
        checked = 0
        warning = 0
        critical = 0
        overdue = 0
        for row in rows:
            checked += 1
            mission = self.watchdog_for_mission(
                row["id"],
                task_db,
                now=now,
            )
            if not mission:
                continue
            level = mission.get("escalation_level")
            warning += int(level == "warning")
            critical += int(level == "critical")
            overdue += int(level == "overdue")
        return {
            "checked": checked,
            "warning": warning,
            "critical": critical,
            "overdue": overdue,
        }

    def attach_root_tasks(self, mission_id: str, root_task_ids: list[str]) -> dict[str, Any]:
        now = now_iso()
        self.db.execute(
            "UPDATE missions SET root_task_ids=?, updated_at=? WHERE id=?",
            (json.dumps(root_task_ids), now, mission_id),
        )
        self.db.commit()
        self.add_timeline_event(
            mission_id,
            "mission.roots_attached",
            {"root_task_ids": root_task_ids},
            status=self.get(mission_id)["status"] if self.get(mission_id) else None,
            created_at=now,
        )
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
        self.add_timeline_event(
            mission_id,
            "mission.task_updated",
            {
                "outcome": outcome or {},
                "aggregate_status": aggregate,
            },
            task_id=task_id,
            status=aggregate,
            created_at=now,
        )
        return self.get(mission_id)

    def resume_failed_tasks(
        self,
        mission_id: str,
        task_db: str | Path,
        task_ids: list[str] | None = None,
        approved_task_ids: set[str] | None = None,
        reason: str = "operator_resume",
    ) -> dict[str, Any]:
        mission = self.get(mission_id)
        if mission is None:
            return {"mission_id": mission_id, "queued": [], "skipped": [], "status": "missing"}
        graph = self.graph_for_mission(mission_id, task_db)
        nodes = {str(node["id"]): node for node in graph.get("nodes", [])}
        requested = list(task_ids) if task_ids is not None else [
            node_id for node_id, node in nodes.items() if node.get("status") == "failed"
        ]
        approved = set(approved_task_ids or set())
        path = Path(task_db)
        queued: list[str] = []
        skipped: list[dict[str, Any]] = []
        if not path.exists():
            return {"mission_id": mission_id, "queued": [], "skipped": [{"reason": "task_db_missing"}], "status": mission["status"]}

        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            now = now_iso()
            for task_id in requested:
                node = nodes.get(task_id)
                if not node or node.get("status") != "failed":
                    skipped.append({"task_id": task_id, "reason": "not_failed_or_not_in_mission"})
                    continue
                row = conn.execute("SELECT payload FROM tasks WHERE id=?", (task_id,)).fetchone()
                if not row:
                    skipped.append({"task_id": task_id, "reason": "task_missing"})
                    continue
                payload = json.loads(row["payload"] or "{}")
                payload["_failed_lane_workers"] = []
                payload["_attempts"] = 0
                payload["_resume_count"] = int(payload.get("_resume_count", 0)) + 1
                if task_id in approved:
                    payload["approved"] = True
                    payload["approved_by"] = "operator"
                conn.execute(
                    "UPDATE tasks SET status='queued', payload=?, updated_at=? WHERE id=?",
                    (json.dumps(payload, ensure_ascii=False), now, task_id),
                )
                conn.execute(
                    "INSERT INTO events(task_id,kind,payload,created_at) VALUES(?,?,?,?)",
                    (
                        task_id,
                        "mission.resume_queued",
                        json.dumps({"mission_id": mission_id, "reason": reason, "approved": task_id in approved}),
                        now,
                    ),
                )
                queued.append(task_id)
                self.add_timeline_event(
                    mission_id,
                    "mission.resume_queued",
                    {"reason": reason, "approved": task_id in approved},
                    task_id=task_id,
                    status="queued",
                    created_at=now,
                )
            conn.commit()
            conn.close()
        except (sqlite3.Error, ValueError, TypeError) as exc:
            return {
                "mission_id": mission_id,
                "queued": queued,
                "skipped": skipped + [{"reason": "resume_failed", "error": str(exc)}],
                "status": mission["status"],
            }

        self.reconcile(task_db)
        refreshed = self.get(mission_id) or mission
        if queued:
            self.add_timeline_event(
                mission_id,
                "mission.resume_completed",
                {"queued_task_ids": queued, "skipped": skipped},
                status=refreshed["status"],
            )
        self.add_audit_event(
            mission_id,
            "mission.resume",
            actor="operator",
            result="success" if queued else "no_change",
            payload={"queued_task_ids": queued, "skipped": skipped, "reason": reason},
        )
        return {
            "mission_id": mission_id,
            "queued": queued,
            "skipped": skipped,
            "status": refreshed["status"],
        }

    def cancel_mission(
        self,
        mission_id: str,
        task_db: str | Path,
        task_ids: list[str] | None = None,
        reason: str = "operator_cancel",
    ) -> dict[str, Any]:
        mission = self.get(mission_id)
        if mission is None:
            return {
                "mission_id": mission_id,
                "status": "missing",
                "cancelled": [],
                "cancellation_requested": [],
                "skipped": [],
            }

        graph = self.graph_for_mission(mission_id, task_db)
        nodes = {str(node["id"]): node for node in graph.get("nodes", [])}
        requested = list(task_ids) if task_ids is not None else [
            node_id for node_id, node in nodes.items()
            if node.get("status") in {"queued", "blocked", "running"}
        ]
        cancelled: list[str] = []
        cancellation_requested: list[str] = []
        skipped: list[dict[str, Any]] = []
        path = Path(task_db)

        if not path.exists():
            return {
                "mission_id": mission_id,
                "status": mission["status"],
                "cancelled": [],
                "cancellation_requested": [],
                "skipped": [{"reason": "task_db_missing"}],
            }

        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            now = now_iso()
            for task_id in requested:
                node = nodes.get(str(task_id))
                if not node:
                    skipped.append({"task_id": task_id, "reason": "not_in_mission"})
                    continue
                current_status = str(node.get("status"))
                row = conn.execute(
                    "SELECT payload FROM tasks WHERE id=?",
                    (task_id,),
                ).fetchone()
                if not row:
                    skipped.append({"task_id": task_id, "reason": "task_missing"})
                    continue

                payload = json.loads(row["payload"] or "{}")
                payload["_cancel_reason"] = reason
                payload["_cancel_requested_by"] = "operator"

                if current_status in {"queued", "blocked"}:
                    payload["cancelled"] = True
                    payload["cancelled_by"] = "operator"
                    conn.execute(
                        "UPDATE tasks SET status='cancelled', payload=?, updated_at=? WHERE id=?",
                        (json.dumps(payload, ensure_ascii=False), now, task_id),
                    )
                    conn.execute(
                        "INSERT INTO events(task_id,kind,payload,created_at) VALUES(?,?,?,?)",
                        (
                            task_id,
                            "task.cancelled",
                            json.dumps({"mission_id": mission_id, "reason": reason}),
                            now,
                        ),
                    )
                    cancelled.append(task_id)
                    self.add_timeline_event(
                        mission_id,
                        "mission.task_cancelled",
                        {"reason": reason, "cancelled_by": "operator"},
                        task_id=task_id,
                        status="cancelled",
                        created_at=now,
                    )
                elif current_status == "running":
                    payload["_cancel_requested"] = True
                    conn.execute(
                        "UPDATE tasks SET payload=?, updated_at=? WHERE id=?",
                        (json.dumps(payload, ensure_ascii=False), now, task_id),
                    )
                    conn.execute(
                        "INSERT INTO events(task_id,kind,payload,created_at) VALUES(?,?,?,?)",
                        (
                            task_id,
                            "task.cancel_requested",
                            json.dumps({
                                "mission_id": mission_id,
                                "reason": reason,
                                "graceful": True,
                            }),
                            now,
                        ),
                    )
                    cancellation_requested.append(task_id)
                    self.add_timeline_event(
                        mission_id,
                        "mission.cancel_requested",
                        {"reason": reason, "graceful": True},
                        task_id=task_id,
                        status="running",
                        created_at=now,
                    )
                else:
                    skipped.append({
                        "task_id": task_id,
                        "reason": "not_cancellable",
                        "status": current_status,
                    })
            conn.commit()
            conn.close()
        except (sqlite3.Error, ValueError, TypeError) as exc:
            return {
                "mission_id": mission_id,
                "status": mission["status"],
                "cancelled": cancelled,
                "cancellation_requested": cancellation_requested,
                "skipped": skipped + [{"reason": "cancel_failed", "error": str(exc)}],
            }

        self.reconcile(task_db)
        refreshed = self.get(mission_id) or mission
        if cancelled or cancellation_requested:
            self.add_timeline_event(
                mission_id,
                "mission.cancel_completed",
                {
                    "cancelled_task_ids": cancelled,
                    "cancellation_requested_task_ids": cancellation_requested,
                    "skipped": skipped,
                },
                status=refreshed["status"],
            )
        return {
            "mission_id": mission_id,
            "status": refreshed["status"],
            "cancelled": cancelled,
            "cancellation_requested": cancellation_requested,
            "skipped": skipped,
        }

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
            completed_at = (
                mission["completed_at"] or now_iso()
                if should_complete
                else None
            )
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
            self.add_timeline_event(
                mission["id"],
                "mission.reconciled",
                {"previous_status": mission["status"], "graph_status": aggregate},
                task_id=latest_task_id,
                status=aggregate,
            )
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
            "cancelled": statuses.count("cancelled"),
        }
        return {
            "mission_id": mission_id,
            "roots": roots,
            "nodes": list(nodes.values()),
            "edges": edges,
            "counts": counts,
        }

    def progress_for_mission(
        self,
        mission_id: str,
        task_db: str | Path,
    ) -> dict[str, Any] | None:
        mission = self.get(mission_id)
        if mission is None:
            return None
        graph = self.graph_for_mission(mission_id, task_db)
        counts = dict(graph.get("counts") or {})
        total = int(counts.get("total", 0))
        succeeded = int(counts.get("succeeded", 0))
        failed = int(counts.get("failed", 0))
        cancelled = int(counts.get("cancelled", 0))
        terminal = succeeded + failed + cancelled
        active = int(counts.get("queued", 0)) + int(counts.get("running", 0)) + int(counts.get("blocked", 0))
        percent = (terminal / total * 100.0) if total else 0.0

        now_dt = datetime.now(timezone.utc)
        created_dt = datetime.fromisoformat(
            str(mission["created_at"]).replace("Z", "+00:00")
        )
        elapsed_seconds = max(0.0, (now_dt - created_dt).total_seconds())
        observed_cycle_seconds = []
        for node in graph.get("nodes", []):
            if node.get("status") not in TERMINAL:
                continue
            try:
                started = datetime.fromisoformat(
                    str(node["created_at"]).replace("Z", "+00:00")
                )
                finished = datetime.fromisoformat(
                    str(node["updated_at"]).replace("Z", "+00:00")
                )
                duration = (finished - started).total_seconds()
            except (KeyError, TypeError, ValueError):
                continue
            if duration >= 0:
                observed_cycle_seconds.append(duration)

        average_cycle_seconds = (
            sum(observed_cycle_seconds) / len(observed_cycle_seconds)
            if observed_cycle_seconds else None
        )
        throughput_per_minute = (
            terminal / (elapsed_seconds / 60.0)
            if terminal and elapsed_seconds > 0
            else None
        )
        eta_seconds = (
            active * average_cycle_seconds
            if active and average_cycle_seconds is not None
            else None
        )

        return {
            "total": total,
            "completed": terminal,
            "succeeded": succeeded,
            "failed": failed,
            "cancelled": cancelled,
            "active": active,
            "percent": round(percent, 2),
            "elapsed_seconds": round(elapsed_seconds, 3),
            "average_cycle_seconds": (
                round(average_cycle_seconds, 3)
                if average_cycle_seconds is not None else None
            ),
            "throughput_per_minute": (
                round(throughput_per_minute, 4)
                if throughput_per_minute is not None else None
            ),
            "eta_seconds": round(eta_seconds, 3) if eta_seconds is not None else None,
            "eta_confidence": (
                "observed_cycle"
                if eta_seconds is not None
                else "insufficient_history"
            ),
        }

    def control_snapshot(
        self,
        mission_id: str,
        task_db: str | Path,
        timeline_limit: int = 120,
    ) -> dict[str, Any] | None:
        """Return the unified operator view of one mission without executing actions."""
        self.watchdog(task_db)
        self.reconcile(task_db)
        mission = self.get(mission_id)
        if mission is None:
            return None
        graph = self.graph_for_mission(mission_id, task_db)
        timeline = self.timeline_for_mission(
            mission_id,
            limit=max(1, min(int(timeline_limit), 200)),
            task_db=task_db,
        )
        counts = dict(graph.get("counts") or {})
        failed = int(counts.get("failed", 0))
        blocked = int(counts.get("blocked", 0))
        running = int(counts.get("running", 0))
        queued = int(counts.get("queued", 0))
        actions = [
            {
                "action": "approve",
                "enabled": blocked > 0,
                "task_ids": [
                    str(node["id"])
                    for node in graph.get("nodes", [])
                    if node.get("status") == "blocked"
                ],
                "reason": "Blocked tasks require operator approval." if blocked else "No blocked tasks.",
            },
            {
                "action": "resume",
                "enabled": failed > 0,
                "task_ids": [
                    str(node["id"])
                    for node in graph.get("nodes", [])
                    if node.get("status") == "failed"
                ],
                "reason": "Failed tasks can be explicitly resumed; policy gates still apply." if failed else "No failed tasks.",
            },
            {
                "action": "cancel",
                "enabled": (queued + blocked + running) > 0,
                "task_ids": [
                    str(node["id"])
                    for node in graph.get("nodes", [])
                    if node.get("status") in {"queued", "blocked", "running"}
                ],
                "reason": (
                    "Queued/blocked tasks cancel immediately; running tasks receive a "
                    "graceful cancellation request."
                    if (queued + blocked + running) > 0
                    else "No active tasks can be cancelled."
                ),
            },
            {
                "action": "refresh",
                "enabled": True,
                "task_ids": [],
                "reason": "Reconcile mission state and reload the control surface.",
            },
        ]
        deadline = None
        escalation = None
        if mission.get("deadline_at"):
            now_dt = datetime.now(timezone.utc)
            deadline_dt = datetime.fromisoformat(
                str(mission["deadline_at"]).replace("Z", "+00:00")
            )
            seconds_to_deadline = (deadline_dt - now_dt).total_seconds()
            overdue_seconds = max(0.0, -seconds_to_deadline)
            deadline = {
                "at": mission["deadline_at"],
                "status": mission.get("watchdog_status", "ok"),
                "checked_at": mission.get("watchdog_checked_at"),
                "overdue_seconds": overdue_seconds,
            }
            escalation = {
                "level": mission.get("escalation_level", "normal"),
                "checked_at": mission.get("escalation_checked_at"),
                "seconds_to_deadline": seconds_to_deadline,
                "warning_before_seconds": mission.get("escalation_warning_seconds", 900.0),
                "critical_before_seconds": mission.get("escalation_critical_seconds", 300.0),
            }
        budget = self.update_budget_status(mission_id, task_db) or self.budget_for_mission(mission_id, task_db)
        attention = self.attention_for_mission(mission_id, limit=50)
        audit = self.audit_for_mission(mission_id, limit=50)
        audit_integrity = self.verify_audit_chain(mission_id)
        policy = self.policy_for_mission(mission_id)
        integrity = self.check_integrity(mission_id, task_db)
        open_attention = self.attention_for_mission(
            mission_id,
            limit=200,
            include_acknowledged=False,
        )
        return {
            "mission_id": mission_id,
            "mission": mission,
            "deadline": deadline,
            "escalation": escalation,
            "budget": budget,
            "progress": self.progress_for_mission(mission_id, task_db),
            "attention": attention,
            "attention_open_count": len(open_attention),
            "audit": audit,
            "audit_integrity": audit_integrity,
            "policy": policy,
            "integrity": integrity,
            "graph": graph,
            "timeline": timeline,
            "actions": actions,
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
    def _timeline_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]) if row["id"] is not None else None,
            "mission_id": row["mission_id"],
            "task_id": row["task_id"],
            "kind": row["kind"],
            "status": row["status"],
            "payload": json.loads(row["payload"] or "{}"),
            "created_at": row["created_at"],
            "source": "mission",
        }

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
            "deadline_at": row["deadline_at"] if "deadline_at" in row.keys() else None,
            "watchdog_status": row["watchdog_status"] if "watchdog_status" in row.keys() else "ok",
            "watchdog_checked_at": row["watchdog_checked_at"] if "watchdog_checked_at" in row.keys() else None,
            "escalation_level": row["escalation_level"] if "escalation_level" in row.keys() else "normal",
            "escalation_warning_seconds": row["escalation_warning_seconds"] if "escalation_warning_seconds" in row.keys() else 900.0,
            "escalation_critical_seconds": row["escalation_critical_seconds"] if "escalation_critical_seconds" in row.keys() else 300.0,
            "escalation_checked_at": row["escalation_checked_at"] if "escalation_checked_at" in row.keys() else None,
            "max_tasks": row["max_tasks"] if "max_tasks" in row.keys() else 256,
            "max_retries": row["max_retries"] if "max_retries" in row.keys() else 8,
            "budget_status": row["budget_status"] if "budget_status" in row.keys() else "ok",
            "budget_checked_at": row["budget_checked_at"] if "budget_checked_at" in row.keys() else None,
            "policy_revision": row["policy_revision"] if "policy_revision" in row.keys() else 1,
            "policy_hash": row["policy_hash"] if "policy_hash" in row.keys() else None,
            "approval_external": bool(row["approval_external"]) if "approval_external" in row.keys() else True,
            "approval_financial": bool(row["approval_financial"]) if "approval_financial" in row.keys() else True,
            "cancellation_mode": row["cancellation_mode"] if "cancellation_mode" in row.keys() else "graceful",
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
        if observed.issubset({"succeeded", "cancelled"}):
            if "cancelled" in observed:
                return "cancelled"
            return "succeeded"
        return fallback
