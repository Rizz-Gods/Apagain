import importlib
import os
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class MediaTranscriptionResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class MediaTranscription:
    id = "media-transcription"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.config_path = self.root / "config" / "production.json"
        self.out_dir = self.root / "data" / "media" / "captions"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "media-transcription"

    def _config(self):
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _configure_cuda_runtime() -> bool:
        paths = []
        for module_name in ("nvidia.cublas.lib", "nvidia.cudnn.lib"):
            try:
                module = importlib.import_module(module_name)
                root = Path(module.__file__).resolve().parent
                for candidate in root.rglob("*.dll"):
                    paths.append(str(candidate.parent))
            except Exception:
                continue
        if not paths:
            return False
        current = os.environ.get("PATH", "").split(os.pathsep)
        os.environ["PATH"] = os.pathsep.join(list(dict.fromkeys(paths + current)))
        return True

    @staticmethod
    def _write_srt(segments, path: Path):
        def stamp(seconds):
            ms = int(round(seconds * 1000))
            h, rem = divmod(ms, 3600000)
            m, rem = divmod(rem, 60000)
            s, ms = divmod(rem, 1000)
            return f"{h:02}:{m:02}:{s:02},{ms:03}"

        lines = []
        for i, segment in enumerate(segments, 1):
            lines += [
                str(i),
                f"{stamp(segment['start'])} --> {stamp(segment['end'])}",
                segment["text"].strip(),
                "",
            ]
        path.write_text("\\n".join(lines), encoding="utf-8")

    def execute(self, action: str, payload: dict) -> MediaTranscriptionResult:
        if action != "transcribe":
            return MediaTranscriptionResult(False, {}, f"Unsupported media-transcription action: {action}")
        source = payload.get("input", {})
        media_ref = str(source.get("media_ref", "")).strip()
        if not media_ref:
            return MediaTranscriptionResult(False, {}, "media_ref is required")
        path = Path(media_ref).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(self.root.resolve()):
            return MediaTranscriptionResult(False, {}, "media_ref must resolve to an OTH workspace file")

        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            return MediaTranscriptionResult(False, {}, f"faster-whisper unavailable: {exc}")

        config = self._config()
        model_name = str(
            source.get("model")
            or config.get("transcription", {}).get("model", "large-v3-turbo")
        )
        model_dir = self.root / "data" / "models" / "whisper"
        model_dir.mkdir(parents=True, exist_ok=True)

        def load_model(device: str, compute: str):
            return WhisperModel(
                model_name,
                device=device,
                compute_type=compute,
                download_root=str(model_dir),
            )

        self._configure_cuda_runtime()
        attempts = [("cuda", "float16"), ("cpu", "int8")]
        last_error = None
        rows = None
        info = None
        device_used = None
        compute_used = None
        for device, compute in attempts:
            try:
                model = load_model(device, compute)
                segments, info = model.transcribe(
                    str(path),
                    beam_size=int(source.get("beam_size", 5)),
                    vad_filter=True,
                    word_timestamps=True,
                )
                device_used = device
                compute_used = compute
                rows = []
                for seg in segments:
                    rows.append({
                        "start": float(seg.start),
                        "end": float(seg.end),
                        "text": seg.text.strip(),
                        "words": [
                            {
                                "start": float(w.start),
                                "end": float(w.end),
                                "word": w.word,
                                "probability": float(w.probability),
                            }
                            for w in (seg.words or [])
                        ],
                    })
                break
            except Exception as exc:
                last_error = exc
                model = None
                continue

        if rows is None or info is None:
            return MediaTranscriptionResult(False, {}, f"Transcription failed: {last_error}", retryable=True)

        stem = path.stem
        base = self.out_dir / stem
        json_path = base.with_suffix(".json")
        srt_path = base.with_suffix(".srt")
        payload_out = {
            "media_ref": str(path.relative_to(self.root)),
            "model": model_name,
            "device": device_used,
            "compute_type": compute_used,
            "language": info.language,
            "language_probability": float(info.language_probability),
            "duration": float(info.duration),
            "segments": rows,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        json_path.write_text(json.dumps(payload_out, indent=2), encoding="utf-8")
        self._write_srt(rows, srt_path)
        return MediaTranscriptionResult(True, {
            **payload_out,
            "json_path": str(json_path.relative_to(self.root)),
            "srt_path": str(srt_path.relative_to(self.root)),
        })


__all__ = ["MediaTranscription", "MediaTranscriptionResult"]
