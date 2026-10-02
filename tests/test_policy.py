import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel

class PolicyTests(unittest.TestCase):
    def test_external_task_can_be_approved(self):
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
            kernel = OTHKernel(root)
            task = kernel.submit("demo", "echo", {"message":"x","risk":"external"})
            self.assertEqual(kernel.dispatch(task.id)["status"], "blocked")
            self.assertEqual(kernel.approve(task.id)["status"], "queued")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
