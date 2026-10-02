import json
import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.core.scheduler import Scheduler

class SchedulerTests(unittest.TestCase):
    def test_tick_creates_due_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "agents.json").write_text('{"agents":[]}')
            (root / "config" / "skills.json").write_text('{"skills":[]}')
            (root / "config" / "policies.json").write_text(
                '{"external_actions_require_approval":true,'
                '"financial_actions_require_approval":true}'
            )
            (root / "config" / "tools.json").write_text('{"tools":[]}')
            (root / "config" / "schedules.json").write_text(json.dumps({
                "schedules": [{
                    "id": "test",
                    "enabled": True,
                    "interval_seconds": 60,
                    "capability": "demo",
                    "action": "echo",
                    "payload": {"message": "scheduled"}
                }]
            }))
            kernel = OTHKernel(root)
            created = Scheduler(root).tick(kernel)
            self.assertEqual(len(created), 1)
            self.assertEqual(kernel.tasks()[0]["status"], "queued")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
