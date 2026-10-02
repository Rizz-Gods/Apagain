import uuid
from pathlib import Path
from .db import Database
from .models import Task, now_iso
from .policy import PolicyGate
from .registry import Registry
from .skills import SkillAcquirer
from .tools import ToolRegistry
from oth.workers.browser import BrowserWorker
from oth.workers.builtin import BuiltinWorker
from oth.workers.external import ExternalAgentWorker

class OTHKernel:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.db = Database(self.root / "data" / "oth.db")
        self.registry = Registry(
            self.root / "config" / "agents.json",
            self.root / "config" / "skills.json",
        )
        self.skill_acquirer = SkillAcquirer(self.root)
        self.policy = PolicyGate(self.root / "config" / "policies.json")
        self.tools = ToolRegistry(self.root / "config" / "tools.json")
        self.workers = [BuiltinWorker()]
        for agent in self.registry.load_agents():
            if agent.metadata.get("mode") == "browser":
                self.workers.append(BrowserWorker(agent))
            else:
                self.workers.append(ExternalAgentWorker(agent))

    def submit(self, capability: str, action: str, payload: dict, priority: int = 50) -> Task:
        task = Task(str(uuid.uuid4()), capability, action, payload, priority)
        self.db.add_task(task)
        self.db.add_event(task.id, "task.queued",
                          {"capability": capability, "action": action},
                          task.created_at)
        return task

    def dispatch(self, task_id: str):
        rows = [r for r in self.db.list_tasks() if r["id"] == task_id]
        if not rows:
            raise ValueError(f"Unknown task: {task_id}")
        row = rows[0]
        import json
        stored_payload = json.loads(row["payload"])
        task_payload = dict(stored_payload)
        if task_payload.get("prompt"):
            task_payload["skill_context"] = self.skill_acquirer.context_for(task_payload["prompt"])
            memories = self.db.recent_memories(row["capability"], 5)
            task_payload["memory_context"] = "\n".join(
                f'{m["created_at"]}: {m["content"]}' for m in memories
            )
        decision = self.policy.check(task_payload)
        if not decision.allowed:
            self.db.update_task(task_id, "blocked", now_iso())
            self.db.add_event(task_id, "task.approval_required", {"reason": decision.reason}, now_iso())
            return {"status": "blocked", "reason": decision.reason}
        self.db.update_task(task_id, "running", now_iso())
        self.db.add_event(task_id, "task.started", {}, now_iso())
        candidates = [w for w in self.workers if w.supports(row["capability"])]
        candidates.sort(
            key=lambda w: (
                float(getattr(w, "agent", None).metadata.get("priority", 50))
                if getattr(w, "agent", None) else 50
            )
            + self.db.agent_health(getattr(w, "id", "builtin"))["reliability"] * 10,
            reverse=True,
        )
        worker = candidates[0] if candidates else None
        if worker is None:
            self.db.update_task(task_id, "blocked", now_iso())
            self.db.add_event(task_id, "task.blocked", {"reason": "no_worker"}, now_iso())
            return {"status": "blocked", "reason": "no_worker"}

        import json
        result = worker.execute(row["action"], task_payload)
        status = "succeeded" if result.success else "failed"
        retry_scheduled = False
        if (not result.success and result.retryable
                and int(stored_payload.get("_attempts", 0))
                < int(stored_payload.get("max_retries", 0))):
            stored_payload["_attempts"] = int(stored_payload.get("_attempts", 0)) + 1
            self.db.update_task_payload(task_id, stored_payload, now_iso())
            self.db.update_task(task_id, "queued", now_iso())
            self.db.add_event(
                task_id, "task.retry_scheduled",
                {"attempt": stored_payload["_attempts"]}, now_iso(),
            )
            retry_scheduled = True
        if not retry_scheduled:
            self.db.update_task(task_id, status, now_iso())
        self.db.record_agent_result(
            getattr(worker, "id", "builtin"),
            result.success,
            result.error,
            now_iso(),
        )
        effective_status = "retry_queued" if retry_scheduled else status
        self.db.add_memory(
            "task_result",
            row["capability"],
            {
                "task_id": task_id,
                "action": row["action"],
                "status": effective_status,
                "error": result.error,
                "output": result.output,
                "retryable": result.retryable,
            },
            now_iso(),
        )
        self.db.add_event(task_id, f"task.{effective_status}",
                          {"output": result.output, "error": result.error,
                           "retryable": result.retryable},
                          now_iso())
        spawned = []
        if result.success:
            for spec in task_payload.get("next", []):
                child_payload = dict(spec.get("payload", {}))
                child_payload["input"] = result.output
                child = self.submit(
                    spec["capability"],
                    spec["action"],
                    child_payload,
                    int(spec.get("priority", 50)),
                )
                spawned.append(child.id)
                self.db.add_event(
                    task_id, "task.spawned",
                    {"child_task_id": child.id, "capability": child.capability},
                    now_iso(),
                )
        return {"status": effective_status, **result.output,
                "error": result.error, "spawned": spawned,
                "retryable": result.retryable}

    def approve(self, task_id: str):
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Unknown task: {task_id}")
        if task["status"] != "blocked":
            return {"status": task["status"], "changed": False}
        import json
        approved_payload = json.loads(task["payload"])
        approved_payload["approved"] = True
        approved_payload["approved_by"] = "operator"
        now = now_iso()
        self.db.update_task_payload(task_id, approved_payload, now)
        self.db.update_task(task_id, "queued", now)
        self.db.add_event(task_id, "task.approved", {"by": "operator"}, now)
        return {"status": "queued", "changed": True}

    def tasks(self):
        return [dict(r) for r in self.db.list_tasks()]

    def close(self):
        self.db.close()
