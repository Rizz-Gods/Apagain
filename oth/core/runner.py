import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from .kernel import OTHKernel

@dataclass
class RunnerStats:
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    blocked: int = 0

class OTHRunner:
    def __init__(self, kernel: OTHKernel, interval: float = 2.0):
        self.kernel = kernel
        self.interval = interval
        self.running = True
        self.stats = RunnerStats()
        from .scheduler import Scheduler
        self.scheduler = Scheduler(kernel.root)

    def stop(self):
        self.running = False

    def run_once(self):
        now = datetime.now(timezone.utc)
        self.kernel.db.reclaim_stale_tasks(
            now.isoformat(),
            (now - timedelta(seconds=600)).isoformat(),
        )
        self.kernel.missions.reconcile(self.kernel.db.path)
        self.kernel.missions.watchdog(
            self.kernel.db.path,
            now=now.isoformat(),
        )
        self.scheduler.tick(self.kernel)
        queued = [t for t in self.kernel.tasks() if t["status"] == "queued"]
        if not queued:
            return None
        queued.sort(key=lambda t: (-t["priority"], t["created_at"]))
        task = queued[0]
        result = self.kernel.dispatch(task["id"])
        self.stats.processed += 1
        status = result.get("status")
        if status == "succeeded":
            self.stats.succeeded += 1
        elif status == "blocked":
            self.stats.blocked += 1
        else:
            self.stats.failed += 1
        return result

    def run_forever(self):
        while self.running:
            self.run_once()
            if self.running:
                time.sleep(self.interval)
