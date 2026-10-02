import tempfile
import unittest
from pathlib import Path

from oth.core.db import Database
from oth.core.social_autopilot import SocialAutopilot


class SocialAutopilotTests(unittest.TestCase):
    def _seed(self, root: Path):
        db = Database(root / "data" / "oth.db")
        db.add_opportunities([{
            "source": "test",
            "query": "appointment scheduling complaints",
            "title": "Appointment Scheduling",
            "url": "https://example.test/appointments",
            "snippet": "Small businesses struggle with manual appointment scheduling.",
            "signal_type": "review",
            "raw": "",
            "discovered_at": "2026-10-02T00:00:00Z",
        }])
        oid = db.get_opportunity_id(
            "test",
            "https://example.test/appointments",
            "appointment scheduling complaints",
        )
        db.score_opportunity(oid, {
            "score": 82,
            "demand": 90,
            "pain": 90,
            "automation": 75,
            "differentiation": 40,
            "reasons": ["test"],
        }, "2026-10-02T00:00:00Z")
        db.close()

    def test_autopilot_selects_and_queues_top_opportunity_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            worker = SocialAutopilot(root)
            first = worker.execute("run", {
                "input": {
                    "min_score": 65,
                    "max_new_campaigns": 1,
                    "platforms": ["linkedin", "x"],
                }
            })
            self.assertTrue(first.success)
            self.assertEqual(len(first.output["created_campaigns"]), 1)
            campaign = first.output["created_campaigns"][0]
            self.assertEqual(len(campaign["content_ids"]), 2)

            second = worker.execute("run", {
                "input": {
                    "min_score": 65,
                    "max_new_campaigns": 1,
                    "platforms": ["linkedin", "x"],
                }
            })
            self.assertTrue(second.success)
            self.assertEqual(second.output["created_campaigns"], [])
            self.assertTrue(second.output["skipped"])

    def test_autopilot_ignores_low_score_opportunities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            worker = SocialAutopilot(root)
            result = worker.execute("run", {
                "input": {"min_score": 90}
            })
            self.assertTrue(result.success)
            self.assertEqual(result.output["created_campaigns"], [])


if __name__ == "__main__":
    unittest.main()
