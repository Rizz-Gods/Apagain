import tempfile
import unittest
from pathlib import Path

from oth.core.automation_designer import AutomationDesigner
from oth.core.kernel import OTHKernel

class AutomationDesignerTests(unittest.TestCase):
    def test_blueprint_is_created(self):
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
            # seed an opportunity so persistence can be exercised
            signal = {
                "source":"test",
                "query":"manual scheduling software",
                "title":"Manual Scheduling Software",
                "url":"https://example.test",
                "snippet":"Customers say scheduling is manual and expensive.",
                "signal_type":"review",
                "quality":1.0,
            }
            kernel.db.add_opportunities([signal])
            oid = kernel.db.get_opportunity_id("test", "https://example.test", "manual scheduling software")
            kernel.db.score_opportunity(oid, {
                "score":80,"demand":80,"pain":90,"automation":85,
                "differentiation":60,"reasons":["manual workflow"]
            }, "2026-01-01T00:00:00+00:00")
            kernel.workers = [AutomationDesigner()]
            t = kernel.submit("automation-design","design",{
                "input":{"opportunities":[{
                    **signal,
                    "score":{"score":80,"demand":80,"pain":90,"automation":85,"differentiation":60}
                }]}
            })
            result = kernel.dispatch(t.id)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["count"], 1)
            self.assertEqual(len(kernel.db.list_blueprints()), 1)
            kernel.close()

if __name__ == "__main__":
    unittest.main()
