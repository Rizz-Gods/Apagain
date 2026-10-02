import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oth.core.media_qa import MediaQA


class MediaQATests(unittest.TestCase):
    def test_valid_render_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            media = root / "render.mp4"
            media.write_bytes(b"video")
            fake = {
                "format": {"duration": "25.0", "size": "5", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
                "streams": [
                    {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
                    {"index": 1, "codec_type": "audio", "codec_name": "aac"},
                ],
            }
            class Proc:
                returncode = 0
                stdout = json.dumps(fake)
                stderr = ""
            with patch("oth.core.media_qa.subprocess.run", return_value=Proc()):
                result = MediaQA(root).execute("check", {"input": {
                    "media_ref": "render.mp4",
                    "resolution": "1080x1920",
                    "max_duration_seconds": 60,
                    "min_duration_seconds": 2,
                }})
            self.assertTrue(result.success)
            self.assertTrue(result.output["passed"])
            self.assertEqual(result.output["issues"], [])

    def test_bad_render_reports_multiple_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            media = root / "bad.mp4"
            media.write_bytes(b"video")
            fake = {
                "format": {"duration": "82.0", "size": "5", "format_name": "mp4"},
                "streams": [
                    {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 640, "height": 360}
                ],
            }
            class Proc:
                returncode = 0
                stdout = json.dumps(fake)
                stderr = ""
            with patch("oth.core.media_qa.subprocess.run", return_value=Proc()):
                result = MediaQA(root).execute("check", {"input": {
                    "media_ref": "bad.mp4",
                    "resolution": "1080x1920",
                    "max_duration_seconds": 60,
                }})
            self.assertTrue(result.success)
            self.assertFalse(result.output["passed"])
            self.assertIn("resolution_mismatch", result.output["issues"])
            self.assertIn("missing_audio_stream", result.output["issues"])
            self.assertIn("duration_exceeded", result.output["issues"])


if __name__ == "__main__":
    unittest.main()
