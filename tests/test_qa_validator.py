import tempfile
import unittest
from pathlib import Path
from oth.core.kernel import OTHKernel
from oth.core.qa_validator import QAValidator

class QAValidatorTests(unittest.TestCase):
    def test_generated_project_passes_required_checks(self):
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
            project = root / "businesses" / "demo"
            project.mkdir(parents=True)
            (project / "manifest.json").write_text(
                '{"title":"Demo","problem":"Manual work","stack":["n8n"]}'
            )
            (project / "workflow.json").write_text(
                '{"trigger":"event","steps":["capture","notify"],'
                '"human_approval":["external","financial","irreversible"]}'
            )
            (project / "README.md").write_text("# Demo")

            kernel = OTHKernel(root)
            kernel.workers = [QAValidator(root)]
            task = kernel.submit("qa-validation","validate",{
                "input":{"projects":[{
                    "project_path":str(project),
                    "opportunity":{"source":"test","url":"https://example.test","query":"demo"}
                }]}
            })
            result = kernel.dispatch(task.id)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["count"], 1)
            self.assertIn(result["results"][0]["status"], ("passed","warnings"))
            if result["results"][0]["status"] == "warnings":
                self.assertEqual(result["next"][0]["capability"], "dependency-provision")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
