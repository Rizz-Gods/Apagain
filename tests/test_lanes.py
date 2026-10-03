import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.workers.builtin import WorkerResult


class LaneWorker:
    def __init__(self, worker_id, fail=True):
        self.id = worker_id
        self.fail = fail
        self.calls = 0

    def supports(self, capability):
        return capability == "lane-demo"

    def execute(self, action, payload):
        self.calls += 1
        if self.fail:
            return WorkerResult(False, {}, f"{self.id} failed", retryable=True)
        return WorkerResult(True, {"worker": self.id, "lane": payload.get("execution_lane")})


class LaneTests(unittest.TestCase):
    def _kernel(self, root):
        (root / "config").mkdir()
        (root / "data").mkdir()
        (root / "config" / "agents.json").write_text('{"agents":[]}', encoding="utf-8")
        (root / "config" / "skills.json").write_text('{"skills":[]}', encoding="utf-8")
        (root / "config" / "policies.json").write_text(
            '{"external_actions_require_approval":true,"financial_actions_require_approval":true}',
            encoding="utf-8",
        )
        (root / "config" / "tools.json").write_text('{"tools":[]}', encoding="utf-8")
        return OTHKernel(root)

    def test_four_lane_handoff_reaches_fourth_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kernel = self._kernel(root)
            ids = ["lane-1", "lane-2", "lane-3", "lane-4"]
            kernel.workforce.workers = {
                worker_id: {
                    "id": worker_id,
                    "name": worker_id,
                    "capabilities": ["lane-demo"],
                    "status": "available",
                    "metadata": {"priority": 100 - index},
                }
                for index, worker_id in enumerate(ids)
            }
            workers = [LaneWorker("lane-1"), LaneWorker("lane-2"),
                       LaneWorker("lane-3"), LaneWorker("lane-4", fail=False)]
            kernel.workers = workers

            task = kernel.submit("lane-demo", "run", {"max_retries": 0})
            result = kernel.dispatch(task.id)

            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["worker"], "lane-4")
            self.assertEqual(result["lane"], 4)
            self.assertIn("evaluation", result)
            self.assertEqual(result["evaluation"]["observations"]["lane_count"], 4)
            self.assertEqual([w.calls for w in workers], [1, 1, 1, 1])
            events = kernel.db.conn.execute(
                "SELECT kind FROM events WHERE task_id=? ORDER BY id", (task.id,)
            ).fetchall()
            kinds = [row["kind"] for row in events]
            self.assertIn("lane.1.failed", kinds)
            self.assertIn("lane.2.failed", kinds)
            self.assertIn("lane.3.failed", kinds)
            self.assertIn("lane.4.succeeded", kinds)
            self.assertIn("task.evaluated", kinds)
            self.assertEqual(sum(1 for x in kinds if x == "lane.switched"), 3)
            kernel.close()

    def test_failed_worker_is_quarantined_for_next_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kernel = self._kernel(root)
            ids = ["lane-a", "lane-b"]
            kernel.workforce.workers = {
                worker_id: {
                    "id": worker_id,
                    "name": worker_id,
                    "capabilities": ["lane-demo"],
                    "status": "available",
                    "metadata": {"priority": 100 - index},
                }
                for index, worker_id in enumerate(ids)
            }
            first = LaneWorker("lane-a")
            second = LaneWorker("lane-b", fail=False)
            kernel.workers = [first, second]

            task = kernel.submit("lane-demo", "run", {"max_retries": 1})
            result = kernel.dispatch(task.id)

            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["worker"], "lane-b")
            self.assertEqual(result["lane"], 2)
            events = kernel.db.conn.execute(
                "SELECT kind FROM events WHERE task_id=? ORDER BY id", (task.id,)
            ).fetchall()
            kinds = [row["kind"] for row in events]
            self.assertIn("lane.1.failed", kinds)
            self.assertIn("lane.2.succeeded", kinds)
            self.assertIn("lane.switched", kinds)
            kernel.close()


if __name__ == "__main__":
    unittest.main()
