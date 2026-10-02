import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.workers.builtin import WorkerResult

class FlakyWorker:
    id = "flaky"

    def __init__(self):
        self.calls = 0

    def supports(self, capability):
        return capability == "flaky"

    def execute(self, action, payload):
        self.calls += 1
        if self.calls == 1:
            return WorkerResult(False, {}, "temporary", retryable=True)
        return WorkerResult(True, {"message": "recovered"})

class RetryTests(unittest.TestCase):
    def test_retryable_failure_requeues_then_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "agents.json").write_text('{"agents":[]}')
            (root / "config" / "skills.json").write_text('{"skills":[]}')
            (root / "config" / "policies.json").write_text(
                '{"external_actions_require_approval":true,'
                '"financial_actions_require_approval":true}'
            )
            (root / "config" / "tools.json").write_text('{"tools":[]}')
            (root / "config" / "schedules.json").write_text('{"schedules":[]}')
            kernel = OTHKernel(root)
            worker = FlakyWorker()
            kernel.workers = [worker]
            task = kernel.submit("flaky", "run", {"max_retries": 1})
            first = kernel.dispatch(task.id)
            self.assertEqual(first["status"], "retry_queued")
            self.assertEqual(kernel.tasks()[0]["status"], "queued")
            second = kernel.dispatch(task.id)
            self.assertEqual(second["status"], "succeeded")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
