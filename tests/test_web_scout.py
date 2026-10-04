import tempfile
import unittest
from pathlib import Path

from oth.core.web_scout import WebScoutHTTPWorker


class WebScoutHTTPTests(unittest.TestCase):
    def test_supports_scout_and_research_fallback(self):
        worker = WebScoutHTTPWorker()
        self.assertTrue(worker.supports("scout"))
        self.assertTrue(worker.supports("research"))
        self.assertFalse(worker.supports("browser"))

    def test_quality_rejects_unrelated_result(self):
        worker = WebScoutHTTPWorker()
        self.assertEqual(
            worker._quality(
                "small business owners software complaints manual spreadsheets",
                "Appointment Portal",
                "A new Flutter project.",
                "https://example.com",
            ),
            0.0,
        )

    def test_quality_accepts_relevant_result(self):
        worker = WebScoutHTTPWorker()
        self.assertGreaterEqual(
            worker._quality(
                "small business owners software complaints manual spreadsheets",
                "Scheduling software for small business owners",
                "Manual spreadsheets and expensive scheduling tools frustrate owners.",
                "https://example.com/scheduling",
            ),
            0.5,
        )

    def test_redirect_url_is_decoded(self):
        worker = WebScoutHTTPWorker()
        # Bing's a1 wrapper is base64url of the final URL.
        import base64
        from urllib.parse import quote

        final = "https://example.com/path"
        token = base64.urlsafe_b64encode(final.encode()).decode().rstrip("=")
        wrapped = "https://www.bing.com/ck/a?u=a1" + quote(token)
        self.assertEqual(worker._target_url(wrapped), final)


if __name__ == "__main__":
    unittest.main()
