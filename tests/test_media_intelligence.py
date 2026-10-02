import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from oth.core.media_ingest import MediaIngest
from oth.core.media_transcription import MediaTranscription


class MediaIntelligenceTests(unittest.TestCase):
    def test_transcription_generates_word_timed_srt(self):
        class FakeSegment:
            start = 0.0
            end = 1.2
            text = "hello world"
            words = [
                types.SimpleNamespace(start=0.0, end=0.5, word="hello", probability=0.99),
                types.SimpleNamespace(start=0.5, end=1.2, word="world", probability=0.98),
            ]

        class FakeInfo:
            language = "en"
            language_probability = 0.99
            duration = 1.2

        class FakeModel:
            def transcribe(self, *args, **kwargs):
                return iter([FakeSegment()]), FakeInfo()

        fake_module = types.SimpleNamespace(
            WhisperModel=lambda *args, **kwargs: FakeModel()
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            media = root / "data" / "media" / "clip.wav"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"fake-audio")
            with patch.dict(sys.modules, {"faster_whisper": fake_module}):
                worker = MediaTranscription(root)
                result = worker.execute("transcribe", {
                    "input": {"media_ref": "data/media/clip.wav", "model": "tiny.en"}
                })

            self.assertTrue(result.success)
            self.assertEqual(result.output["language"], "en")
            srt = (root / result.output["srt_path"]).read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 --> 00:00:01,200", srt)
            self.assertIn("hello world", srt)

    def test_transcription_falls_back_from_cuda(self):
        class FakeInfo:
            language = "en"
            language_probability = 0.5
            duration = 0.5

        class FakeModel:
            def __init__(self, device):
                self.device = device
            def transcribe(self, *args, **kwargs):
                if self.device == "cuda":
                    raise RuntimeError("cublas64_12.dll missing")
                return iter([]), FakeInfo()

        class FakeFactory:
            def __call__(self, model, device, compute_type, download_root):
                return FakeModel(device)

        fake_module = types.SimpleNamespace(WhisperModel=FakeFactory())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            media = root / "clip.wav"
            media.write_bytes(b"audio")
            with patch.dict(sys.modules, {"faster_whisper": fake_module}):
                worker = MediaTranscription(root)
                result = worker.execute("transcribe", {
                    "input": {"media_ref": str(media), "model": "tiny.en"}
                })
            self.assertTrue(result.success)
            self.assertEqual(result.output["device"], "cpu")

    def test_ingest_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            info = root / "data" / "media" / "ingest" / "abc.info.json"
            info.parent.mkdir(parents=True)
            info.write_text(json.dumps({
                "id": "abc",
                "webpage_url": "https://example.com/video",
                "title": "Example",
                "uploader": "Example",
                "duration": 42,
            }), encoding="utf-8")

            class Result:
                returncode = 0
                stderr = ""
                stdout = ""

            with patch("oth.core.media_ingest.subprocess.run", return_value=Result()):
                worker = MediaIngest(root)
                result = worker.execute("download", {"input": {"url": "https://example.com/video"}})

            self.assertTrue(result.success)
            self.assertEqual(result.output["sources"][0]["source_id"], "abc")
            self.assertEqual(result.output["sources"][0]["title"], "Example")


if __name__ == "__main__":
    unittest.main()
