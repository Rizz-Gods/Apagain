import json
import tempfile
import unittest
from pathlib import Path

from oth.core.social_queue import SocialQueueManager


class SocialQueueTests(unittest.TestCase):
    def _seed(self, root):
        path = Path(root) / "data" / "social_queue.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "items": [{
                "id": "item-1",
                "content_id": "content-1",
                "campaign_id": "campaign-1",
                "platform": "linkedin",
                "payload": {"text": "hello"},
                "status": "queued",
                "approval": {"required": True, "status": "pending"},
            }]
        }))

    def test_approval_changes_queue_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._seed(tmp)
            worker = SocialQueueManager(tmp)
            result = worker.execute("approve", {"input": {"content_id": "content-1"}})
            self.assertTrue(result.success)
            self.assertEqual(result.output["item"]["approval"]["status"], "approved")
            self.assertEqual(result.output["item"]["status"], "queued")

    def test_reconcile_holds_unapproved_and_spawns_approved_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._seed(tmp)
            worker = SocialQueueManager(tmp)
            pending = worker.execute("reconcile", {"input": {}})
            self.assertTrue(pending.success)
            self.assertEqual(pending.output["dispatches"], [])
            self.assertEqual(
                pending.output["held"][0]["reason"],
                "awaiting_approval",
            )

            worker.execute("approve", {"input": {"content_id": "content-1"}})
            ready = worker.execute("reconcile", {"input": {}})
            self.assertEqual(len(ready.output["dispatches"]), 1)
            spec = ready.output["dispatches"][0]
            self.assertEqual(spec["capability"], "social-actions")
            self.assertTrue(spec["payload"]["approved"])
            self.assertEqual(
                spec["payload"]["input"]["content_id"],
                "content-1",
            )

            persisted = json.loads(
                (Path(tmp) / "data" / "social_queue.json").read_text()
            )
            self.assertEqual(persisted["items"][0]["status"], "dispatching")

    def test_reconcile_recovers_stale_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "social_queue.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "items": [{
                    "id": "item-2",
                    "content_id": "content-2",
                    "platform": "x",
                    "payload": {"text": "hello"},
                    "status": "dispatching",
                    "updated_at": "2020-01-01T00:00:00+00:00",
                    "approval": {"required": True, "status": "approved"},
                }]
            }))
            worker = SocialQueueManager(tmp)
            result = worker.execute("reconcile", {"input": {}})
            self.assertTrue(result.success)
            self.assertEqual(len(result.output["dispatches"]), 1)


if __name__ == "__main__":
    unittest.main()
