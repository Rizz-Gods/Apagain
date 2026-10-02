import uuid
from pathlib import Path
from .db import Database
from .models import Task, now_iso
from .registry import Registry
from oth.workers.builtin import BuiltinWorker

class OTHKernel:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.db = Database(self.root / "data" / "oth.db")
        self.registry = Registry(
            self.root / "config" / "agents.json",
            self.root / "config" / "skills.json",
        )
        self.workers = [BuiltinWorker()]

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
        self.db.update_task(task_id, "running", now_iso())
        self.db.add_event(task_id, "task.started", {}, now_iso())
        worker = next((w for w in self.workers if w.supports(row["capability"])), None)
        if worker is None:
            self.db.update_task(task_id, "blocked", now_iso())
            self.db.add_event(task_id, "task.blocked", {"reason": "no_worker"}, now_iso())
            return {"status": "blocked", "reason": "no_worker"}

        import json
        result = worker.execute(row["action"], json.loads(row["payload"]))
        status = "succeeded" if result.success else "failed"
        self.db.update_task(task_id, status, now_iso())
        self.db.add_event(task_id, f"task.{status}",
                          {"output": result.output, "error": result.error},
                          now_iso())
        return {"status": status, **result.output, "error": result.error}

    def tasks(self):
        return [dict(r) for r in self.db.list_tasks()]

    def close(self):
        self.db.close()
