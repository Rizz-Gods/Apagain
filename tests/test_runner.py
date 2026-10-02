import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.core.runner import OTHRunner

class RunnerTests(unittest.TestCase):
    def test_run_once_processes_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "agents.json").write_text('{"agents":[]}')
            (root / "config" / "skills.json").write_text(
                '{"skills":[{"id":"builtin.echo","name":"Echo",'
                '"version":"1.0.0","capabilities":["demo"]}]}'
            )
            kernel = OTHKernel(root)
            task = kernel.submit("demo", "echo", {"message": "runner"})
            result = OTHRunner(kernel).run_once()
            self.assertEqual(task.id, kernel.tasks()[0]["id"])
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(kernel.tasks()[0]["status"], "succeeded")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
