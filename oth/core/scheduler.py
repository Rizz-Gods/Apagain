import json
import time
import uuid
from pathlib import Path

class Scheduler:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.config_path = self.root / "config" / "schedules.json"
        self.state_path = self.root / "data" / "schedule-state.json"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def _config(self):
        if not self.config_path.exists():
            return {"schedules": []}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _state(self):
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save_state(self, state):
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def tick(self, kernel):
        now = time.time()
        config = self._config()
        state = self._state()
        created = []
        changed = False
        for job in config.get("schedules", []):
            if not job.get("enabled", True):
                continue
            sid = job["id"]
            next_run = float(state.get(sid, 0))
            if now < next_run:
                continue
            payload = dict(job.get("payload", {}))
            task = kernel.submit(
                job["capability"], job["action"], payload,
                int(job.get("priority", 50)),
            )
            interval = max(float(job.get("interval_seconds", 60)), 1)
            state[sid] = now + interval
            changed = True
            created.append(task.id)
        if changed:
            self._save_state(state)
        return created
