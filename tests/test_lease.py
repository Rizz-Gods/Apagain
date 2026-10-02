import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from oth.core.kernel import OTHKernel

class LeaseTests(unittest.TestCase):
    def test_stale_running_task_is_reclaimed(self):
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
            (root / "config" / "schedules.json").write_text('{"schedules":[]}')
            kernel = OTHKernel(root)
            task = kernel.submit("demo", "echo", {"message":"stale"})
            kernel.db.update_task(task.id, "running", "2020-01-01T00:00:00+00:00")
            now = datetime.now(timezone.utc)
            reclaimed = kernel.db.reclaim_stale_tasks(
                now.isoformat(),
                (now - timedelta(seconds=600)).isoformat(),
            )
            self.assertEqual(reclaimed, 1)
            self.assertEqual(kernel.tasks()[0]["status"], "failed")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
