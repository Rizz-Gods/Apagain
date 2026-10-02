import json
import tempfile
import unittest
from pathlib import Path

from oth.core.social_control import SocialControl


class SocialControlTests(unittest.TestCase):
    def test_status_aggregates_campaign_queue_and_funnel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "data" / "social_autopilot.json").write_text(json.dumps({
                "campaigns": [{
                    "campaign_id": "campaign-1",
                    "market": "B2B founders",
                    "score": 82,
                    "status": "queued_for_review",
                    "platforms": ["linkedin"],
                    "created_at": "2026-10-02T00:00:00Z",
                }]
            }))
            (root / "data" / "social_queue.json").write_text(json.dumps({
                "items": [{
                    "campaign_id": "campaign-1",
                    "content_id": "content-1",
                    "platform": "linkedin",
                    "status": "queued",
                    "approval": {"status": "pending"},
                }]
            }))
            (root / "data" / "social_leads.json").write_text(json.dumps({
                "leads": [{
                    "campaign_id": "campaign-1",
                    "status": "converted",
                }]
            }))
            (root / "data" / "social_accounts.json").write_text(json.dumps({
                "accounts": [{
                    "provider": "linkedin",
                    "account_label": "linkedin",
                    "status": "ready",
                    "credential_present": True,
                    "identity": {"actor": "urn:li:person:123"},
                    "capabilities": ["publish_posts", "analytics"],
                    "last_probe_at": "2026-10-02T00:00:00Z",
                }]
            }))
            worker = SocialControl(root)
            result = worker.execute("status", {"input": {}})
            self.assertTrue(result.success)
            row = result.output["campaigns"][0]
            self.assertEqual(row["queue"]["awaiting_approval"], 1)
            self.assertEqual(row["funnel"]["conversions"], 1)
            self.assertEqual(result.output["totals"]["conversions"], 1)
            self.assertEqual(result.output["attention"][0]["priority"], "human_review")
            self.assertEqual(result.output["accounts"][0]["identity"]["actor"], "urn:li:person:123")
            self.assertEqual(result.output["account_attention"], [])


if __name__ == "__main__":
    unittest.main()
