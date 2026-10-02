import json
import tempfile
import unittest
from pathlib import Path

from oth.core.social_autonomy import SocialAutonomy


class SocialAutonomyTests(unittest.TestCase):
    def test_command_persists_pilot_intent_and_tick_creates_adaptive_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "autonomy.json").write_text(json.dumps({
                "enabled": True,
                "mode": "autonomous-ops",
                "initiative": {
                    "max_new_campaigns_per_tick": 1,
                    "max_content_coverage_hours": 36,
                },
                "decision_rules": {
                    "min_opportunity_score": 65,
                    "min_content_coverage_hours": 36,
                }
            }))
            worker = SocialAutonomy(root)
            command = worker.execute("command", {
                "input": {"instruction": "Prioritize practical short-form education and avoid generic engagement bait."}
            })
            self.assertTrue(command.success)
            pilot = json.loads((root / "data" / "pilot_state.json").read_text())
            self.assertIn("generic engagement bait", " ".join(pilot["constraints"] + pilot["preferences"]).lower() or "x")
            tick = worker.execute("tick", {"input": {}})
            self.assertTrue(tick.success)
            kinds = {x["capability"] for x in tick.output["initiatives"]}
            self.assertIn("social-autopilot", kinds)
            self.assertIn("social-analytics", kinds)


if __name__ == "__main__":
    unittest.main()
