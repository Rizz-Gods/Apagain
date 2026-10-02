import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oth.core.resolve_bridge import ResolveBridge


class ResolveBridgeTests(unittest.TestCase):
    def test_status_reports_not_installed_when_resolve_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "production.json").write_text(json.dumps({
                "executable_candidates": [str(root / "Resolve.exe")]
            }))
            worker = ResolveBridge(root)
            result = worker.execute("status", {"input": {}})
            self.assertTrue(result.success)
            self.assertFalse(result.output["installed"])
            self.assertFalse(result.output["external_scripting_ready"])

    def test_prepare_project_exposes_requirements_before_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "production.json").write_text(json.dumps({
                "executable_candidates": [str(root / "Resolve.exe")]
            }))
            worker = ResolveBridge(root)
            result = worker.execute("prepare_project", {"input": {
                "manifest": {"project_name": "AP Social Engine", "campaign_id": "c1"}
            }})
            self.assertTrue(result.success)
            self.assertEqual(result.output["status"], "waiting_for_resolve")


if __name__ == "__main__":
    unittest.main()
