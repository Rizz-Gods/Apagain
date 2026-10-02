import json
import os
import tempfile
import unittest
from pathlib import Path

from oth.core.social_accounts import SocialAccountManager
from oth.core.social_optimizer import SocialOptimizer

class SocialAccountAndOptimizerTests(unittest.TestCase):
    def test_setup_never_persists_secret_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            os.environ["OTH_SOCIAL_LINKEDIN_TOKEN"] = "secret-test-value"
            try:
                worker = SocialAccountManager(root)
                result = worker.execute("setup", {"input": {"provider": "linkedin"}})
                self.assertTrue(result.success)
                self.assertTrue(result.output["checklist"][0]["configured"])
                self.assertNotIn("secret-test-value", json.dumps(result.output))
            finally:
                os.environ.pop("OTH_SOCIAL_LINKEDIN_TOKEN", None)

    def test_optimizer_recommends_from_recorded_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = SocialOptimizer(root)
            worker.execute("record", {
                "input": {
                    "platform": "linkedin",
                    "content_id": "a",
                    "hook": "manual work is killing sales",
                    "format": "carousel",
                    "pillar": "pain",
                    "metrics": {
                        "impressions": 1000,
                        "engagements": 100,
                        "qualified_leads": 12,
                        "conversions": 2,
                    },
                }
            })
            result = worker.execute("optimize", {"input": {"platform": "linkedin"}})
            self.assertTrue(result.success)
            self.assertEqual(result.output["best"][0]["content_id"], "a")
            self.assertTrue(result.output["recommendations"])
            self.assertEqual(len(result.output["next_experiments"]), 3)

if __name__ == "__main__":
    unittest.main()
