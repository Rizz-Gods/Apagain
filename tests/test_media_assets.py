import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oth.core.media_assets import MediaAssetManager

class MediaAssetTests(unittest.TestCase):
    @staticmethod
    def fake_probe(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = json.dumps({
                "format": {
                    "format_name": "mp4",
                    "duration": "12.5",
                    "size": "100",
                },
                "streams": [{
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1280,
                    "height": 720,
                }],
            })
            stderr = ""
        return Result()

    def test_inspect_stays_inside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "data" / "media" / "demo.mp4"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"demo")
            with patch("oth.core.media_assets.subprocess.run", side_effect=self.fake_probe):
                worker = MediaAssetManager(root)
                result = worker.execute("inspect", {"input": {"media_ref": "data/media/demo.mp4"}})
            self.assertTrue(result.success)
            self.assertEqual(result.output["metadata"]["format"]["format_name"], "mp4")

    def test_rejects_path_outside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = Path(tmp).parent / "outside-media.mp4"
            outside.write_bytes(b"outside")
            try:
                worker = MediaAssetManager(root)
                result = worker.execute("inspect", {"input": {"media_ref": str(outside)}})
                self.assertFalse(result.success)
                self.assertIn("inside the OTH workspace", result.error)
            finally:
                outside.unlink(missing_ok=True)
    def test_register_is_idempotent_by_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "data" / "media" / "demo.mp4"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"same-content")
            with patch("oth.core.media_assets.subprocess.run", side_effect=self.fake_probe):
                worker = MediaAssetManager(root)
                first = worker.execute("register", {"input": {"media_ref": "data/media/demo.mp4"}})
                second = worker.execute("register", {"input": {"media_ref": "data/media/demo.mp4"}})
            self.assertTrue(first.success)
            self.assertTrue(second.success)
            self.assertEqual(first.output["asset"]["media_id"], second.output["asset"]["media_id"])
            data = json.loads((root / "data" / "media_assets.json").read_text())
            self.assertEqual(len(data["assets"]), 1)

    def test_normalize_uses_configured_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "data" / "media" / "demo.mov"
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b"movie")
            commands = []
            def fake_run(command, **kwargs):
                commands.append(command)
                if "ffprobe" in command[0]:
                    class ProbeResult:
                        returncode = 0
                        stdout = json.dumps({"format": {"format_name": "mov", "duration": "12.5", "size": "100"}, "streams": [{"codec_type": "video", "codec_name": "h264"}]})
                        stderr = ""
                    return ProbeResult()
                target = Path(command[-1])
                target.write_bytes(b"normalized")
                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return Result()
            with patch("oth.core.media_assets.subprocess.run", side_effect=fake_run):
                worker = MediaAssetManager(root)
                result = worker.execute("normalize", {"input": {"media_ref": "data/media/demo.mov"}})
            self.assertTrue(result.success)
            self.assertTrue(result.output["media_ref"].endswith(".mp4"))
            self.assertTrue(any("libx264" in command for command in commands))
            self.assertTrue(Path(result.output["asset"]["normalized_path"]).is_file())

if __name__ == "__main__":
    unittest.main()
