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
CREATE TABLE IF NOT EXISTS trigger_fires (
  fire_key TEXT PRIMARY KEY, fired_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_edges (
  parent_task_id TEXT NOT NULL,
  child_task_id TEXT NOT NULL UNIQUE,
  edge_type TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL,
  capability TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  quality REAL NOT NULL,
  success INTEGER NOT NULL,
  lane INTEGER NOT NULL,
  observations TEXT NOT NULL,
  lesson TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  query TEXT NOT NULL,
  title TEXT,
  url TEXT,
  snippet TEXT,
  signal_type TEXT NOT NULL,
  raw TEXT NOT NULL,
  discovered_at TEXT NOT NULL,
  UNIQUE(source, url, query)
);
CREATE TABLE IF NOT EXISTS opportunity_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER NOT NULL UNIQUE,
  score REAL NOT NULL,
  demand REAL NOT NULL,
  pain REAL NOT NULL,
  automation REAL NOT NULL,
  differentiation REAL NOT NULL,
  reasons TEXT NOT NULL,
  scored_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS automation_blueprints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER NOT NULL UNIQUE,
  title TEXT NOT NULL,
  problem TEXT NOT NULL,
  automation TEXT NOT NULL,
  workflow TEXT NOT NULL,
  stack TEXT NOT NULL,
  estimated_complexity TEXT NOT NULL,
  blueprint_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS build_artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER NOT NULL,
  project_path TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS qa_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER NOT NULL,
  project_path TEXT NOT NULL,
  status TEXT NOT NULL,
  checks_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  errors_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS promotion_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER NOT NULL,
  project_path TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
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

    def trigger_fired(self, fire_key: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM trigger_fires WHERE fire_key=?",
            (fire_key,),
        ).fetchone()
        return row is not None

    def mark_trigger_fired(self, fire_key: str, fired_at: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO trigger_fires(fire_key,fired_at) VALUES(?,?)",
            (fire_key, fired_at),
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

    def add_opportunities(self, signals: list[dict[str, Any]]):
        for s in signals:
            self.conn.execute(
                "INSERT OR IGNORE INTO opportunities(source,query,title,url,snippet,signal_type,raw,discovered_at) VALUES(?,?,?,?,?,?,?,?)",
                (s.get("source",""), s.get("query",""), s.get("title",""),
                 s.get("url",""), s.get("snippet",""), s.get("signal_type","demand"),
                 s.get("raw",""), s.get("discovered_at","")),
            )
        self.conn.commit()

    def get_opportunity_id(self, source: str, url: str, query: str):
        row = self.conn.execute(
            "SELECT id FROM opportunities WHERE source=? AND url=? AND query=?",
            (source, url, query),
        ).fetchone()
        return row["id"] if row else None

    def list_opportunities(self, limit: int = 50):
        return self.conn.execute(
            "SELECT * FROM opportunities ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def score_opportunity(self, opportunity_id: int, score: dict[str, Any], scored_at: str):
        self.conn.execute(
            "INSERT INTO opportunity_scores(opportunity_id,score,demand,pain,automation,differentiation,reasons,scored_at) "
            "VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(opportunity_id) DO UPDATE SET score=excluded.score,demand=excluded.demand,"
            "pain=excluded.pain,automation=excluded.automation,differentiation=excluded.differentiation,"
            "reasons=excluded.reasons,scored_at=excluded.scored_at",
            (opportunity_id, score["score"], score["demand"], score["pain"],
             score["automation"], score["differentiation"], json.dumps(score["reasons"]), scored_at),
        )
        self.conn.commit()

    def top_opportunities(self, limit: int = 20):
        return self.conn.execute(
            "SELECT o.*, s.score, s.demand, s.pain, s.automation, s.differentiation, s.reasons "
            "FROM opportunities o JOIN opportunity_scores s ON s.opportunity_id=o.id "
            "ORDER BY s.score DESC LIMIT ?", (limit,)
        ).fetchall()

    def add_blueprint(self, opportunity_id: int, blueprint: dict[str, Any], created_at: str):
        self.conn.execute(
            "INSERT INTO automation_blueprints(opportunity_id,title,problem,automation,workflow,stack,estimated_complexity,blueprint_json,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(opportunity_id) DO UPDATE SET title=excluded.title,problem=excluded.problem,"
            "automation=excluded.automation,workflow=excluded.workflow,stack=excluded.stack,"
            "estimated_complexity=excluded.estimated_complexity,blueprint_json=excluded.blueprint_json,"
            "created_at=excluded.created_at",
            (opportunity_id, blueprint["title"], blueprint["problem"],
             blueprint["automation"], json.dumps(blueprint["workflow"]),
             json.dumps(blueprint["stack"]), blueprint["estimated_complexity"],
             json.dumps(blueprint), created_at),
        )
        self.conn.commit()

    def list_blueprints(self, limit: int = 20):
        return self.conn.execute(
            "SELECT * FROM automation_blueprints ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def add_build_artifact(self, opportunity_id: int, project_path: str,
                           manifest: dict[str, Any], status: str, created_at: str):
        self.conn.execute(
            "INSERT INTO build_artifacts(opportunity_id,project_path,manifest_json,status,created_at) "
            "VALUES(?,?,?,?,?)",
            (opportunity_id, project_path, json.dumps(manifest), status, created_at),
        )
        self.conn.commit()

    def list_build_artifacts(self, limit: int = 20):
        return self.conn.execute(
            "SELECT * FROM build_artifacts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def add_qa_result(self, opportunity_id: int, project_path: str,
                      status: str, checks: list, warnings: list,
                      errors: list, created_at: str):
        self.conn.execute(
            "INSERT INTO qa_results(opportunity_id,project_path,status,checks_json,warnings_json,errors_json,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (opportunity_id, project_path, status,
             json.dumps(checks), json.dumps(warnings),
             json.dumps(errors), created_at),
        )
        self.conn.commit()

    def list_qa_results(self, limit: int = 20):
        return self.conn.execute(
            "SELECT * FROM qa_results ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def update_build_status(self, project_path: str, status: str):
        self.conn.execute(
            "UPDATE build_artifacts SET status=? WHERE project_path=?",
            (status, project_path),
        )
        self.conn.commit()

    def add_promotion_result(self, opportunity_id: int, project_path: str,
                             status: str, reason: str, created_at: str):
        self.conn.execute(
            "INSERT INTO promotion_results(opportunity_id,project_path,status,reason,created_at) VALUES(?,?,?,?,?)",
            (opportunity_id, project_path, status, reason, created_at),
        )
        self.conn.commit()

    def list_promotion_results(self, limit: int = 20):
        return self.conn.execute(
            "SELECT * FROM promotion_results ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def record_evaluation(
        self,
        task_id: str,
        capability: str,
        worker_id: str,
        quality: float,
        success: bool,
        lane: int,
        observations: dict[str, Any],
        lesson: str,
        created_at: str,
    ) -> None:
        self.conn.execute(
            "INSERT INTO evaluations(task_id,capability,worker_id,quality,success,lane,observations,lesson,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                capability,
                worker_id,
                float(quality),
                int(success),
                int(lane),
                json.dumps(observations),
                lesson,
                created_at,
            ),
        )
        self.conn.commit()

    def recent_evaluations(self, worker_id: str | None = None, limit: int = 20):
        if worker_id:
            return self.conn.execute(
                "SELECT * FROM evaluations WHERE worker_id=? ORDER BY id DESC LIMIT ?",
                (worker_id, limit),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM evaluations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def engineering_scorecard(self, worker_ids: list[str] | None = None, limit: int = 20):
        if worker_ids is None:
            rows = self.conn.execute(
                "SELECT DISTINCT agent_id FROM agent_stats "
                "WHERE agent_id LIKE '%engineer%' OR agent_id LIKE '%engineering%'"
            ).fetchall()
            worker_ids = [row["agent_id"] for row in rows]
        if not worker_ids:
            return []
        placeholders = ",".join("?" for _ in worker_ids)
        query = (
            "SELECT a.agent_id AS worker_id, "
            "(a.successes + a.failures) AS runs, "
            "a.successes, a.failures, "
            "ROUND(CASE WHEN (a.successes + a.failures) > 0 "
            "THEN CAST(a.successes AS REAL) / (a.successes + a.failures) ELSE 1.0 END, 4) AS reliability, "
            "COUNT(e.id) AS evaluated_runs, "
            "ROUND(COALESCE(AVG(e.quality), 0.0), 4) AS avg_quality, "
            "ROUND(COALESCE(AVG(e.lane), 0.0), 2) AS avg_lane, "
            "a.last_run "
            "FROM agent_stats a "
            "LEFT JOIN evaluations e ON e.worker_id=a.agent_id AND e.capability='engineering' "
            f"WHERE a.agent_id IN ({placeholders}) "
            "GROUP BY a.agent_id "
            "ORDER BY reliability DESC, avg_quality DESC LIMIT ?"
        )
        rows = self.conn.execute(query, (*worker_ids, limit)).fetchall()
        enriched = []
        for row in rows:
            item = dict(row)
            latest = self.conn.execute(
                "SELECT observations, lesson, created_at "
                "FROM evaluations WHERE worker_id=? AND capability='engineering' "
                "ORDER BY id DESC LIMIT 1",
                (row["worker_id"],),
            ).fetchone()
            metadata = {}
            if latest:
                try:
                    metadata = json.loads(latest["observations"] or "{}")
                except (TypeError, ValueError):
                    metadata = {}
                item.update({
                    "last_provider": metadata.get("provider"),
                    "last_model": metadata.get("model"),
                    "last_tier": metadata.get("tier"),
                    "last_complexity": metadata.get("complexity"),
                    "last_attempts": metadata.get("attempts"),
                    "last_implementation_changed": metadata.get("implementation_changed"),
                    "last_verification_passed": metadata.get("verification_passed"),
                    "last_lesson": latest["lesson"],
                    "last_evaluation": latest["created_at"],
                })
            enriched.append(item)
        return enriched

    def worker_circuit_state(self, worker_id: str, failure_threshold: int = 3, window: int = 12) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT kind,payload,created_at FROM events "
            "WHERE kind LIKE 'lane.%' ORDER BY id DESC LIMIT ?",
            (window,),
        ).fetchall()
        consecutive_failures = 0
        seen_worker = False
        last_event = None
        for row in rows:
            kind = str(row["kind"])
            try:
                payload = json.loads(row["payload"])
            except (TypeError, ValueError):
                continue
            if payload.get("worker_id") != worker_id:
                continue
            seen_worker = True
            last_event = kind
            if kind.endswith(".failed"):
                consecutive_failures += 1
            elif kind.endswith(".succeeded"):
                break
        return {
            "open": consecutive_failures >= max(int(failure_threshold), 1),
            "consecutive_failures": consecutive_failures,
            "last_event": last_event,
            "seen": seen_worker,
        }

    def agent_quality(self, agent_id: str) -> float:
        row = self.conn.execute(
            "SELECT AVG(quality) AS quality FROM evaluations WHERE worker_id=?",
            (agent_id,),
        ).fetchone()
        if not row or row["quality"] is None:
            return 1.0
        return float(row["quality"])

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
            return {
                "successes": 0,
                "failures": 0,
                "reliability": 1.0,
                "quality": self.agent_quality(agent_id),
            }
        total = row["successes"] + row["failures"]
        reliability = row["successes"] / total if total else 1.0
        return {
            "successes": row["successes"],
            "failures": row["failures"],
            "reliability": reliability,
            "quality": self.agent_quality(agent_id),
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

    def add_task_edge(self, parent_task_id: str, child_task_id: str, edge_type: str, created_at: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO task_edges(parent_task_id,child_task_id,edge_type,created_at) VALUES(?,?,?,?)",
            (parent_task_id, child_task_id, edge_type, created_at),
        )
        self.conn.commit()

    def task_children(self, parent_task_id: str):
        return self.conn.execute(
            "SELECT e.*, t.capability, t.action, t.status, t.priority "
            "FROM task_edges e JOIN tasks t ON t.id=e.child_task_id "
            "WHERE e.parent_task_id=? ORDER BY t.priority DESC, t.created_at ASC",
            (parent_task_id,),
        ).fetchall()

    def task_parent(self, child_task_id: str):
        return self.conn.execute(
            "SELECT e.*, t.capability, t.action, t.status, t.priority "
            "FROM task_edges e JOIN tasks t ON t.id=e.parent_task_id "
            "WHERE e.child_task_id=?",
            (child_task_id,),
        ).fetchone()

    def task_graph(self, task_id: str, depth: int = 8) -> dict[str, Any]:
        root = self.get_task(task_id)
        if root is None:
            return {"root": None, "nodes": [], "edges": []}
        nodes = {}
        edges = []
        frontier = [root["id"]]
        levels = {root["id"]: 0}
        while frontier:
            current = frontier.pop(0)
            level = levels[current]
            row = self.get_task(current)
            if row is not None:
                nodes[current] = {
                    "id": row["id"],
                    "capability": row["capability"],
                    "action": row["action"],
                    "status": row["status"],
                    "priority": row["priority"],
                    "level": level,
                }
            if level >= depth:
                continue
            for child in self.task_children(current):
                edges.append({
                    "parent_task_id": current,
                    "child_task_id": child["child_task_id"],
                    "edge_type": child["edge_type"],
                })
                if child["child_task_id"] not in levels:
                    levels[child["child_task_id"]] = level + 1
                    frontier.append(child["child_task_id"])
        return {"root": task_id, "nodes": list(nodes.values()), "edges": edges}

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

    def reclaim_stale_tasks(self, now_iso: str, cutoff_iso: str):
        rows = self.conn.execute(
            "SELECT id FROM tasks WHERE status='running' AND updated_at < ?",
            (cutoff_iso,),
        ).fetchall()
        for row in rows:
            self.conn.execute(
                "UPDATE tasks SET status='failed', updated_at=? WHERE id=?",
                (now_iso, row["id"]),
            )
            self.conn.execute(
                "INSERT INTO events(task_id,kind,payload,created_at) VALUES(?,?,?,?)",
                (row["id"], "task.lease_expired",
                 json.dumps({"reason": "worker_lease_expired"}), now_iso),
            )
        self.conn.commit()
        return len(rows)

    def list_tasks(self):
        return self.conn.execute(
            "SELECT * FROM tasks ORDER BY priority DESC, created_at ASC"
        ).fetchall()

    def close(self):
        self.conn.close()
