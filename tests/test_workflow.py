import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.core.runner import OTHRunner

class WorkflowTests(unittest.TestCase):
    def test_success_spawns_next_task(self):
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
            task = kernel.submit("demo", "echo", {
                "message": "stage-1",
                "next": [{"capability":"demo","action":"echo"}]
            })
            result = kernel.dispatch(task.id)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(len(result["spawned"]), 1)
            self.assertEqual(kernel.tasks()[-1]["status"], "queued")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
