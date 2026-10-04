import tempfile
import unittest
from pathlib import Path

from oth.core.resilient_fallbacks import (
    SocialAccountsFallback,
    SocialAutonomyFallback,
    SocialAutopilotFallback,
    SocialControlFallback,
    SocialLeadsFallback,
    SocialMarketFallback,
)


class SocialCoreResilienceTests(unittest.TestCase):
    def test_accounts_fallback_stays_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = SocialAccountsFallback(tmp).execute(
                "onboard", {"input": {"provider": "linkedin"}}
            )
            self.assertTrue(result.success)
            self.assertFalse(result.output["checklist"][0]["live_oauth"])

    def test_autonomy_fallback_observes_without_external_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = SocialAutonomyFallback(tmp).execute(
                "tick", {"input": {"queue": [
                    {"approval": {"status": "pending"}}
                ]}}
            )
            self.assertTrue(result.success)
            self.assertFalse(result.output["external_actions"])

    def test_autopilot_fallback_builds_review_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = SocialAutopilotFallback(tmp).execute("run", {
                "input": {
                    "min_score": 60,
                    "max_new_campaigns": 1,
                    "candidates": [{"title": "Example", "score": 90}],
                }
            })
            self.assertTrue(result.success)
            self.assertEqual(
                result.output["created_campaigns"][0]["status"],
                "queued_for_review",
            )

    def test_control_fallback_surfaces_attention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            (data / "social_queue.json").write_text(
                '{"items":[{"approval":{"status":"pending"},"status":"queued"}]}'
            )
            result = SocialControlFallback(tmp).execute("attention", {"input": {}})
            self.assertTrue(result.success)
            self.assertEqual(result.output["pending_approval"], 1)

    def test_leads_fallback_requires_consent_for_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialLeadsFallback(tmp)
            created = worker.execute("ingest", {
                "input": {
                    "contact": "buyer@example.test",
                    "message": "pricing please",
                    "consent": False,
                }
            })
            self.assertTrue(created.success)
            follow = worker.execute("followup_draft", {
                "input": {"lead_id": created.output["lead"]["id"]}
            })
            self.assertFalse(follow.success)

    def test_market_fallback_stays_inbound_and_approval_gated(self):
        result = SocialMarketFallback(".").execute("plan", {
            "input": {"market": "B2B founders", "offer": "automation audit"}
        })
        self.assertTrue(result.success)
        self.assertEqual(result.output["strategy"], "inbound_first")
        self.assertIn("external", result.output["human_approval"])


if __name__ == "__main__":
    unittest.main()
