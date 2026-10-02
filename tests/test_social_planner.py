import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oth.core.social_planner import SocialPlanner

class SocialPlannerTests(unittest.TestCase):
    def _seed(self, root):
        data = Path(root) / "data" / "social_queue.json"
        data.parent.mkdir(parents=True, exist_ok=True)
        data.write_text(json.dumps({
            "items": [
                {
                    "content_id": "a",
                    "campaign_id": "c1",
                    "platform": "linkedin",
                    "status": "queued",
                    "approval": {"status": "pending"},
                },
                {
                    "content_id": "b",
                    "campaign_id": "c1",
                    "platform": "x",
                    "status": "queued",
                    "approval": {"status": "approved"},
                },
            ]
        }))

    def test_preview_does_not_mutate_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "social_schedule.json").write_text(json.dumps({
                "timezone": "Asia/Kolkata",
                "slot_gap_minutes": 60,
                "windows": {"linkedin": ["10:00"], "x": ["11:00"]},
            }))
            self._seed(root)
            planner = SocialPlanner(root)
            result = planner.execute("preview", {"input": {}})
            self.assertTrue(result.success)
            self.assertEqual(result.output["count"], 2)
            queue = json.loads((root / "data" / "social_queue.json").read_text())
            self.assertNotIn("due_at", queue["items"][0])

    def test_plan_sets_due_at_without_approving(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "social_schedule.json").write_text(json.dumps({
                "timezone": "Asia/Kolkata",
                "slot_gap_minutes": 60,
                "windows": {"linkedin": ["10:00"], "x": ["11:00"]},
            }))
            self._seed(root)
            planner = SocialPlanner(root)
            result = planner.execute("plan", {"input": {}})
            self.assertTrue(result.success)
            data = json.loads((root / "data" / "social_queue.json").read_text())
            for item in data["items"]:
                self.assertIsNotNone(item.get("due_at"))
            self.assertEqual(data["items"][0]["approval"]["status"], "pending")
            self.assertEqual(data["items"][1]["approval"]["status"], "approved")
            self.assertFalse(result.output["approval_bypassed"])

    def test_planner_is_idempotent_for_existing_due_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "social_schedule.json").write_text(json.dumps({
                "timezone": "Asia/Kolkata",
                "slot_gap_minutes": 60,
                "windows": {"linkedin": ["10:00"], "x": ["11:00"]},
            }))
            self._seed(root)
            planner = SocialPlanner(root)
            planner.execute("plan", {"input": {}})
            first = json.loads((root / "data" / "social_queue.json").read_text())
            planner.execute("plan", {"input": {}})
            second = json.loads((root / "data" / "social_queue.json").read_text())
            self.assertEqual(
                [x["due_at"] for x in first["items"]],
                [x["due_at"] for x in second["items"]],
            )

if __name__ == "__main__":
    unittest.main()
