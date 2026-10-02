import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel

class KernelTests(unittest.TestCase):
    def test_submit_and_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            (root / "config").mkdir()
            (root / "config" / "agents.json").write_text('{"agents":[]}')
            (root / "config" / "skills.json").write_text(
                '{"skills":[{"id":"builtin.echo","name":"Echo",'
                '"version":"1.0.0","capabilities":["demo"]}]}'
            )
            kernel = OTHKernel(root)
            task = kernel.submit("demo", "echo", {"message": "OTH online"})
            result = kernel.dispatch(task.id)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["message"], "OTH online")
            self.assertEqual(kernel.tasks()[0]["status"], "succeeded")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
