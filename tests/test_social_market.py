import json
import tempfile
import unittest
from pathlib import Path

from oth.core.social_market import SocialMarketWorker

class SocialMarketTests(unittest.TestCase):
    def test_social_market_creates_inbound_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            config = {
                "platforms": {
                    "linkedin": {"mode": "api_first", "capabilities": ["publish_posts"]},
                    "youtube": {"mode": "api_first", "capabilities": ["upload_video"]},
                    "x": {"mode": "api_first", "capabilities": ["publish_posts"]},
                }
            }
            (root / "config" / "social_platforms.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            worker = SocialMarketWorker(root)
            result = worker.execute("plan", {
                "input": {
                    "market": "AI automation agencies",
                    "offer": "automation audit",
                    "platforms": ["linkedin", "youtube", "x"],
                }
            })
            self.assertTrue(result.success)
            self.assertEqual(result.output["count"], 6)
            self.assertEqual(result.output["platforms"], ["linkedin", "youtube", "x"])
            path = Path(result.output["workflow_path"])
            self.assertTrue(path.exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["strategy"], "inbound_first")
            self.assertEqual(len(data["workflows"]), 6)
            self.assertIn("lead", json.dumps(data).lower())
            self.assertIn("external", data["human_approval"])
            self.assertIn("financial", data["human_approval"])
            self.assertIn("irreversible", data["human_approval"])
            project = Path(result.output["project_path"])
            self.assertTrue((project / "manifest.json").exists())
            self.assertTrue((project / "workflow.json").exists())
            self.assertEqual(result.output["next"][0]["capability"], "workflow-compile")
            self.assertEqual(result.output["projects"][0]["project_path"], str(project))

if __name__ == "__main__":
    unittest.main()
