import json
import tempfile
import unittest
from pathlib import Path

from oth.core.resilient_fallbacks import (
    AutomationBuilderFallback,
    QAFallback,
    PromotionFallback,
    DependencyProvisionFallback,
    WorkflowCompilerFallback,
    MediaQAFallback,
    MediaTranscriptionFallback,
)
from oth.core.workforce import WorkforceRegistry


class ResilientFallbackTests(unittest.TestCase):
    def test_registry_has_independent_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "workforce.json").write_text(
                json.dumps({
                    "defaults": {
                        "department": "ops",
                        "permissions": ["read", "local_execute"]
                    },
                    "capabilities": {},
                    "workers": {
                        "automation-builder-fallback": {
                            "department": "engineering",
                            "permissions": ["read", "local_execute"]
                        }
                    }
                }),
                encoding="utf-8",
            )
            registry = WorkforceRegistry(root)
            contract = registry.contract_for("automation-builder-fallback")
            self.assertEqual(contract.department, "engineering")
            self.assertIn("local_execute", contract.permissions)

    def test_builder_and_compiler_fallbacks_create_safe_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            builder = AutomationBuilderFallback(root)
            built = builder.execute("build", {
                "input": {"blueprints": [{
                    "quality": 1.0,
                    "score": {"score": 90},
                    "blueprint": {
                        "title": "Fallback Demo",
                        "problem": "manual work",
                        "automation": "automate it",
                        "workflow": ["capture", "notify"],
                        "stack": ["Python"],
                    },
                }]}
            })
            self.assertTrue(built.success)
            project = Path(built.output["projects"][0]["project_path"])
            compiler = WorkflowCompilerFallback(root)
            compiled = compiler.execute("compile", {"input": {"projects": [{"project_path": str(project)}]}})
            self.assertTrue(compiled.success)
            self.assertTrue((project / "oth.workflow.fallback.json").exists())
            self.assertFalse(compiled.output["compiled"][0]["active"])

    def test_qa_promotion_dependency_fallbacks_are_conservative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "businesses" / "demo"
            project.mkdir(parents=True)
            (project / "manifest.json").write_text("{}", encoding="utf-8")
            (project / "workflow.json").write_text(
                json.dumps({"name": "Demo", "steps": ["capture"]}),
                encoding="utf-8",
            )
            (project / "README.md").write_text("# Demo", encoding="utf-8")

            qa = QAFallback(root).execute("validate", {"input": {"projects": [{"project_path": str(project)}]}})
            self.assertTrue(qa.success)
            self.assertEqual(qa.output["results"][0]["status"], "passed")

            promo = PromotionFallback().execute("promote", {
                "input": {"results": [{"project_path": str(project), "status": "warnings"}]}
            })
            self.assertEqual(promo.output["decisions"][0]["status"], "held")

            plan = DependencyProvisionFallback().execute("plan", {
                "input": {"warnings": ["n8n dependency missing", "n8n dependency missing"]}
            })
            self.assertEqual(plan.output["count"], 1)

    def test_media_fallbacks_never_claim_full_probe_or_asr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "clip.mp4"
            media.write_bytes(b"x")
            qa = MediaQAFallback(root).execute("check", {"input": {"media_ref": str(media)}})
            self.assertTrue(qa.success)
            self.assertEqual(qa.output["verification_mode"], "filesystem-structural")
            tx = MediaTranscriptionFallback(root).execute("transcribe", {
                "input": {"media_ref": str(media), "transcript_text": "hello world"}
            })
            self.assertTrue(tx.success)
            self.assertEqual(tx.output["mode"], "sidecar-import")


if __name__ == "__main__":
    unittest.main()

