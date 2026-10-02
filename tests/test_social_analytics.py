import json
import os
import tempfile
import unittest
from pathlib import Path

from oth.core.social_analytics import SocialAnalytics
class SocialAnalyticsTests(unittest.TestCase):
    def test_youtube_fetch_normalizes_metrics(self):
        calls = []

        def requester(method, url, token, headers=None, body=None):
            calls.append((method, url, token, headers))
            return 200, {
                "items": [{
                    "id": "video-1",
                    "statistics": {
                        "viewCount": "1200",
                        "likeCount": "84",
                        "commentCount": "16",
                    },
                }]
            }

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["OTH_SOCIAL_YOUTUBE_TOKEN"] = "yt-test"
            try:
                worker = SocialAnalytics(tmp, requester=requester)
                result = worker.execute("fetch", {"input": {
                    "platform": "youtube",
                    "external_id": "video-1",
                    "content_id": "content-y",
                }})
                self.assertTrue(result.success)
                metrics = result.output["record"]["metrics"]
                self.assertEqual(metrics["impressions"], 1200)
                self.assertEqual(metrics["engagements"], 100)
                self.assertEqual(calls[0][0], "GET")
                self.assertIn("www.googleapis.com/youtube/v3/videos", calls[0][1])
                self.assertTrue(result.output["next"])
            finally:
                os.environ.pop("OTH_SOCIAL_YOUTUBE_TOKEN", None)
    def test_missing_youtube_credentials_does_not_network(self):
        calls = []

        def requester(*args, **kwargs):
            calls.append((args, kwargs))
            return 500, {}

        with tempfile.TemporaryDirectory() as tmp:
            os.environ.pop("OTH_SOCIAL_YOUTUBE_TOKEN", None)
            worker = SocialAnalytics(tmp, requester=requester)
            result = worker.execute("fetch", {"input": {
                "platform": "youtube",
                "external_id": "video-1",
                "content_id": "content-y",
            }})
            self.assertTrue(result.success)
            self.assertEqual(result.output["status"], "awaiting_credentials")
            self.assertEqual(calls, [])
    def test_linkedin_fetch_maps_metrics_and_headers(self):
        calls = []

        def requester(method, url, token, headers=None, body=None):
            calls.append((method, url, token, headers))
            return 200, {"elements": [{"total": {"value": 123}}]}

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["OTH_SOCIAL_LINKEDIN_TOKEN"] = "li-test"
            try:
                worker = SocialAnalytics(tmp, requester=requester)
                result = worker.execute("fetch", {"input": {
                    "platform": "linkedin",
                    "external_id": "urn:li:share:123",
                    "content_id": "content-li",
                }})
                self.assertTrue(result.success)
                metrics = result.output["record"]["metrics"]
                self.assertEqual(metrics["impressions"], 123)
                self.assertEqual(metrics["reach"], 123)
                self.assertEqual(metrics["shares"], 123)
                self.assertEqual(metrics["reactions"], 123)
                self.assertEqual(metrics["comments"], 123)
                self.assertEqual(metrics["engagements"], 369)
                self.assertEqual(len(calls), 5)
                self.assertEqual(calls[0][3]["Linkedin-Version"], "202608")
                self.assertEqual(calls[0][3]["X-Restli-Protocol-Version"], "2.0.0")
                self.assertTrue(result.output["next"])
            finally:
                os.environ.pop("OTH_SOCIAL_LINKEDIN_TOKEN", None)
    def test_manual_record_and_list_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = SocialAnalytics(tmp)
            result = worker.execute("record", {"input": {
                "platform": "linkedin",
                "content_id": "manual-1",
                "external_id": "urn:test",
                "metrics": {"impressions": 50, "engagements": 5},
            }})
            self.assertTrue(result.success)
            listed = worker.execute("list", {"input": {}})
            self.assertEqual(len(listed.output["items"]), 1)
            self.assertEqual(listed.output["items"][0]["metrics"]["impressions"], 50)

    def test_sync_reads_published_queue_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "data" / "social_queue.json"
            queue.parent.mkdir(parents=True, exist_ok=True)
            queue.write_text(json.dumps({"items": [{
                "content_id": "published-1",
                "campaign_id": "campaign-1",
                "platform": "youtube",
                "status": "published",
                "external_response": {"id": "video-2"},
                "payload": {"format": "short_or_video"},
            }]}))
            os.environ["OTH_SOCIAL_YOUTUBE_TOKEN"] = "yt-test"
            try:
                def requester(method, url, token, headers=None, body=None):
                    return 200, {"items": [{
                        "id": "video-2",
                        "statistics": {
                            "viewCount": "500",
                            "likeCount": "20",
                            "commentCount": "5",
                        },
                    }]}

                worker = SocialAnalytics(root, requester=requester)
                result = worker.execute("sync", {"input": {}})
                self.assertTrue(result.success)
                self.assertEqual(result.output["synced"], 1)
                self.assertEqual(len(result.output["next"]), 1)
                self.assertEqual(
                    result.output["next"][0]["payload"]["input"]["content_id"],
                    "published-1",
                )
            finally:
                os.environ.pop("OTH_SOCIAL_YOUTUBE_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
