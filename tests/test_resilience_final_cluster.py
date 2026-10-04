import tempfile
import unittest
from pathlib import Path

from oth.core.resilient_fallbacks import (
    MediaAssetsFallback,
    MediaIngestFallback,
    MediaProductionFallback,
    SocialQueueFallback,
    SocialActionsFallback,
)


class FinalResilienceClusterTests(unittest.TestCase):
    def test_media_assets_fallback_is_filesystem_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "clip.mp4"
            media.write_bytes(b"video")
            worker = MediaAssetsFallback(root)
            inspected = worker.execute("inspect", {"input": {"media_ref": "clip.mp4"}})
            self.assertTrue(inspected.success)
            self.assertEqual(inspected.output["inspection_mode"], "filesystem")
            registered = worker.execute("register", {"input": {"media_ref": "clip.mp4"}})
            self.assertTrue(registered.success)
            normalized = worker.execute("normalize", {"input": {"media_ref": "clip.mp4"}})
            self.assertEqual(normalized.output["asset"]["normalization_mode"], "already_compatible")

    def test_media_ingest_never_silently_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = MediaIngestFallback(tmp)
            result = worker.execute("download", {
                "input": {"url": "https://example.test/video", "title": "Example"}
            })
            self.assertTrue(result.success)
            self.assertFalse(result.output["sources"][0]["network"])
            self.assertEqual(result.output["status"], "awaiting_download_backend")

    def test_media_production_returns_provider_neutral_manifest(self):
        result = MediaProductionFallback().execute("plan", {
            "input": {
                "briefs": [{
                    "brief_id": "b1",
                    "campaign_id": "c1",
                    "platform": "instagram",
                    "format": "reel",
                    "duration_seconds": 30,
                }]
            }
        })
        self.assertTrue(result.success)
        manifest = result.output["manifests"][0]
        self.assertEqual(manifest["status"], "ready_for_primary_renderer")
        self.assertEqual(manifest["template"]["aspect_ratio"], "9:16")

    def test_social_queue_fallback_preserves_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialQueueFallback(tmp)
            worker.execute("approve", {"input": {"content_id": "missing"}})
            root = Path(tmp)
            path = root / "data" / "social_queue_fallback.json"
            path.write_text(
                '{"items":[{"content_id":"c1","platform":"linkedin","payload":{"text":"hello"},"approval":{"status":"approved"}}]}'
            )
            result = worker.execute("reconcile", {"input": {}})
            self.assertTrue(result.success)
            self.assertFalse(result.output["external_actions"])
            self.assertEqual(result.output["dispatches"][0]["capability"], "social-actions")

    def test_social_actions_fallback_never_calls_provider(self):
        worker = SocialActionsFallback()
        doctor = worker.execute("doctor", {"input": {}})
        self.assertTrue(doctor.success)
        self.assertFalse(doctor.output["live_actions_available"])

        publish = worker.execute("publish_text", {
            "input": {"provider": "linkedin", "text": "hello"}
        })
        self.assertTrue(publish.success)
        self.assertFalse(publish.output["executed"])
        self.assertFalse(publish.output["live"])


if __name__ == "__main__":
    unittest.main()

