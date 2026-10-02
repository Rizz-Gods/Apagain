import json
import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.core.workflow_compiler import WorkflowCompiler

class WorkflowCompilerTests(unittest.TestCase):
    def test_compile_writes_inactive_n8n_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "businesses" / "demo"
            project.mkdir(parents=True)
            (project / "manifest.json").write_text(
                '{"title":"Demo Automation","workflow":[]}'
            )
            (project / "workflow.json").write_text(
                '{"trigger":"event","steps":["capture","notify"]}'
            )
            worker = WorkflowCompiler(root)
            result = worker.execute("compile", {
                "input": {"projects": [{
                    "project_path": str(project),
                    "opportunity": {
                        "source":"test","url":"https://example.test","query":"demo"
                    }
                }]}
            })
            self.assertTrue(result.success)
            path = project / "n8n.workflow.json"
            self.assertTrue(path.exists())
            data = json.loads(path.read_text())
            self.assertFalse(data["active"])
            self.assertEqual(len(data["nodes"]), 3)

if __name__ == "__main__":
    unittest.main()
