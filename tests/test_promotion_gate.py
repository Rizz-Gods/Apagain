import tempfile
import unittest
from pathlib import Path
from oth.core.kernel import OTHKernel
from oth.core.promotion_gate import PromotionGate

class PromotionGateTests(unittest.TestCase):
    def test_warnings_are_held(self):
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
            kernel.workers = [PromotionGate()]
            task = kernel.submit("promotion-gate","promote",{
                "input":{"results":[{
                    "project_path":"businesses/demo",
                    "status":"warnings",
                    "opportunity":{"source":"test","url":"https://example.test","query":"demo"}
                }]}
            })
            result = kernel.dispatch(task.id)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["decisions"][0]["status"], "held")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
