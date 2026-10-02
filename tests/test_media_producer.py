import json
import tempfile
import unittest
from pathlib import Path

from oth.core.media_producer import MediaProducer


class MediaProducerTests(unittest.TestCase):
    def test_produces_platform_specific_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = MediaProducer(tmp)
            result = worker.execute("plan", {"input": {"briefs": [{
                "brief_id": "brief-instagram-1",
                "campaign_id": "campaign-1",
                "platform": "instagram",
                "purpose": "discovery",
                "funnel_stage": "awareness",
                "format": "reel",
                "duration_seconds": 25,
                "hook": "Manual follow-up is leaking revenue.",
                "claim": "Teams lose time on repetitive scheduling.",
                "proof": "Show the automated workflow.",
                "sources": ["campaign evidence"],
                "edit_recipe": ["hook", "proof", "cta"],
            }]}})
            self.assertTrue(result.success)
            manifest = result.output["manifests"][0]
            self.assertEqual(manifest["template"]["aspect_ratio"], "9:16")
            self.assertEqual(manifest["render"]["resolution"], "1080x1920")
            self.assertEqual(manifest["status"], "ready_for_resolve")
            self.assertEqual(result.output["next"][0]["capability"], "resolve-bridge")


if __name__ == "__main__":
    unittest.main()
