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

    def test_queue_runs_content_qa_before_enqueue(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialContentEngine(tmp)
            result = worker.execute("queue", {
                "input": {
                    "campaign_id": "qa-fail",
                    "market": "B2B founders",
                    "offer": "automation audit",
                    "pain": "x" * 281,
                    "proof": "",
                    "cta": "",
                    "platforms": ["x"],
                }
            })
            self.assertFalse(result.success)
            self.assertEqual(result.output["package"]["qa"]["status"], "failed")

    def test_queue_is_idempotent_for_campaign_and_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialContentEngine(tmp)
            payload = {
                "input": {
                    "campaign_id": "campaign-1",
                    "market": "B2B founders",
                    "offer": "automation audit",
                    "platforms": ["linkedin"],
                }
            }
            first = worker.execute("queue", payload)
            second = worker.execute("queue", payload)
            self.assertTrue(first.success)
            self.assertTrue(second.success)
            self.assertEqual(first.output["queued"][0]["content_id"], second.output["queued"][0]["content_id"])

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
