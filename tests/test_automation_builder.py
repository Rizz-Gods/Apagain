import tempfile
import unittest
from pathlib import Path

from oth.core.automation_builder import AutomationBuilder
from oth.core.kernel import OTHKernel

class AutomationBuilderTests(unittest.TestCase):
    def test_build_creates_project_artifact(self):
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
            kernel.workers = [AutomationBuilder(root)]
            t = kernel.submit("automation-build","build",{
                "input":{"blueprints":[{
                    "source":"test",
                    "url":"https://example.test",
                    "query":"manual scheduling",
                    "quality":1.0,
                    "score":{"score":80},
                    "blueprint":{
                        "title":"Automation blueprint: Manual Scheduling",
                        "problem":"Scheduling is manual",
                        "automation":"Automate scheduling",
                        "workflow":["capture","validate","notify"],
                        "stack":["n8n","Python"],
                        "estimated_complexity":"low"
                    }
                }]}
            })
            result = kernel.dispatch(t.id)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["count"], 1)
            project = root / "businesses" / "automation-blueprint-manual-scheduling"
            self.assertTrue((project / "manifest.json").exists())
            self.assertTrue((project / "workflow.json").exists())
            kernel.close()

if __name__ == "__main__":
    unittest.main()
