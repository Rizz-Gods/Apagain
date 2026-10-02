import tempfile
import unittest
from pathlib import Path

from oth.core.social_actions import SocialActionBus
from oth.core.social_content import SocialContentEngine


class SocialContentTests(unittest.TestCase):
    def test_draft_creates_platform_native_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialContentEngine(tmp)
            result = worker.execute("draft", {
                "input": {
                    "market": "B2B founders",
                    "offer": "AI sales automation audit",
                    "pain": "Manual lead follow-up is leaking revenue.",
                    "proof": "The workflow map identifies the repetitive steps worth automating first.",
                    "cta": "Reply with your current sales workflow.",
                }
            })
            self.assertTrue(result.success)
            variants = result.output["package"]["variants"]
            self.assertEqual(
                set(variants),
                {"linkedin", "x", "youtube", "instagram"},
            )
            self.assertIn("text", variants["linkedin"])
            self.assertIn("title", variants["youtube"])
            self.assertIn("caption", variants["instagram"])

    def test_queue_is_local_and_approval_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialContentEngine(tmp)
            result = worker.execute("queue", {
                "input": {
                    "market": "B2B founders",
                    "offer": "AI sales automation audit",
                    "platforms": ["linkedin", "instagram"],
                }
            })
            self.assertTrue(result.success)
            self.assertEqual(len(result.output["queued"]), 2)
            self.assertTrue(all(
                item["approval"]["status"] == "pending"
                for item in result.output["queued"]
            ))
            self.assertTrue((Path(tmp) / "data" / "social_queue.json").exists())

    def test_prepare_publish_handles_supported_and_media_edges(self):
        worker = SocialActionBus()
        ready = worker.execute("prepare_publish", {
            "input": {
                "provider": "linkedin",
                "text": "Ready to review.",
            }
        })
        self.assertTrue(ready.success)
        self.assertEqual(ready.output["status"], "ready_for_approval")
        self.assertTrue(ready.output["live_action_available"])

        media = worker.execute("prepare_publish", {
            "input": {
                "provider": "instagram",
                "text": "A visual post.",
                "media_required": True,
            }
        })
        self.assertTrue(media.success)
        self.assertEqual(media.output["status"], "needs_input")
        self.assertFalse(media.output["live_action_available"])

    def test_prepare_publish_enforces_platform_limits(self):
        worker = SocialActionBus()
        result = worker.execute("prepare_publish", {
            "input": {
                "provider": "x",
                "text": "x" * 281,
            }
        })
        self.assertFalse(result.success)
        self.assertIn("limit", result.error)


if __name__ == "__main__":
    unittest.main()
