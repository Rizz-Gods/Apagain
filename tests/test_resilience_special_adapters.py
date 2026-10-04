import tempfile
import unittest

from oth.core.resilient_fallbacks import BrowserHTTPFallback, ResolveBridgeFallback


class SpecialAdapterResilienceTests(unittest.TestCase):
    def test_browser_http_fallback_reads_without_ui_claim(self):
        worker = BrowserHTTPFallback()
        result = worker.execute("command", {
            "command": "wait",
            "args": ["1"],
        })
        self.assertTrue(result.success)
        self.assertFalse(result.output["browser_ui"])

    def test_resolve_fallback_never_claims_external_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = ResolveBridgeFallback(tmp)
            status = worker.execute("status", {"input": {}})
            self.assertTrue(status.success)
            self.assertEqual(status.output["render_capability"], "plan_only")
            render = worker.execute("render", {
                "input": {
                    "manifest_id": "m1",
                    "render": {"resolution": "1080x1920"},
                }
            })
            self.assertTrue(render.success)
            self.assertFalse(render.output["rendered"])
            self.assertEqual(render.output["status"], "awaiting_primary_renderer")


if __name__ == "__main__":
    unittest.main()
