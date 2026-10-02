import tempfile
import unittest

from oth.core.social_leads import SocialLeadEngine


class SocialLeadTests(unittest.TestCase):
    def test_ingest_scores_buyer_intent_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialLeadEngine(tmp)
            first = worker.execute("ingest", {
                "input": {
                    "platform": "linkedin",
                    "external_id": "42",
                    "message": "Interested. What is the pricing and can I book a demo?",
                    "contact": "buyer@example.com",
                    "consent": True,
                    "content_id": "b2b-linkedin-1",
                    "campaign_id": "sales-audit-oct",
                }
            })
            self.assertTrue(first.success)
            self.assertTrue(first.output["created"])
            lead = first.output["lead"]
            self.assertEqual(lead["intent"], "buyer_intent")
            self.assertGreaterEqual(lead["score"], 80)

            second = worker.execute("ingest", {
                "input": {
                    "platform": "linkedin",
                    "external_id": "42",
                    "message": "Still interested.",
                    "contact": "buyer@example.com",
                    "consent": True,
                }
            })
            self.assertTrue(second.success)
            self.assertFalse(second.output["created"])

    def test_followup_requires_consent(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialLeadEngine(tmp)
            result = worker.execute("ingest", {
                "input": {
                    "platform": "x",
                    "external_id": "7",
                    "message": "Tell me more.",
                    "consent": False,
                }
            })
            lead_id = result.output["lead"]["id"]
            followup = worker.execute("followup_draft", {
                "input": {"lead_id": lead_id}
            })
            self.assertFalse(followup.success)
            self.assertIn("consent", followup.error.lower())

    def test_summary_tracks_content_to_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialLeadEngine(tmp)
            result = worker.execute("ingest", {
                "input": {
                    "platform": "linkedin",
                    "external_id": "conv-1",
                    "message": "What is the price?",
                    "consent": True,
                    "content_id": "post-77",
                }
            })
            lead_id = result.output["lead"]["id"]
            qualified = worker.execute("qualify", {"input": {"lead_id": lead_id}})
            self.assertTrue(qualified.success)
            converted = worker.execute("convert", {"input": {"lead_id": lead_id}})
            self.assertTrue(converted.success)
            summary = worker.execute("summary", {"input": {}})
            row = summary.output["content_summary"][0]
            self.assertEqual(row["content_id"], "post-77")
            self.assertEqual(row["qualified_leads"], 1)
            self.assertEqual(row["conversions"], 1)
            self.assertEqual(summary.output["next"][0]["action"], "ingest_funnel")

    def test_consented_followup_is_drafted_not_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialLeadEngine(tmp)
            result = worker.execute("ingest", {
                "input": {
                    "platform": "youtube",
                    "message": "How do I start? I want a trial.",
                    "consent": True,
                }
            })
            followup = worker.execute("followup_draft", {
                "input": {"lead_id": result.output["lead"]["id"]}
            })
            self.assertTrue(followup.success)
            self.assertEqual(
                followup.output["approval"],
                "required_before_external_send",
            )
            self.assertIn("next step", followup.output["draft"].lower())


if __name__ == "__main__":
    unittest.main()
