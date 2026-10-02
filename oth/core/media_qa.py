import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class MediaQAResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class MediaQA:
    id = "media-qa"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.config_path = self.root / "config" / "production.json"

    def supports(self, capability: str) -> bool:
        return capability == "media-qa"

    def _config(self):
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _probe(self, path: Path):
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries",
                "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,r_frame_rate",
                "-of", "json", str(path)
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "ffprobe failed")
        return json.loads(proc.stdout or "{}")

    def execute(self, action: str, payload: dict) -> MediaQAResult:
        if action != "check":
            return MediaQAResult(False, {}, f"Unsupported media-qa action: {action}")

        source = payload.get("input", {})
        media_ref = str(source.get("media_ref", "")).strip()
        if not media_ref:
            return MediaQAResult(False, {}, "media_ref is required")

        path = Path(media_ref).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(self.root):
            return MediaQAResult(False, {}, "media_ref must resolve inside the OTH workspace")

        try:
            probe = self._probe(path)
        except Exception as exc:
            return MediaQAResult(False, {}, str(exc), retryable=True)

        cfg = self._config().get("qa", {})
        streams = probe.get("streams", [])
        format_info = probe.get("format", {})
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

        issues = []
        if not video:
            issues.append("missing_video_stream")
        if not audio and cfg.get("require_audio", True):
            issues.append("missing_audio_stream")

        if video:
            expected_resolution = source.get("resolution")
            if expected_resolution:
                try:
                    width, height = [int(x) for x in str(expected_resolution).lower().split("x", 1)]
                    if int(video.get("width", 0)) != width or int(video.get("height", 0)) != height:
                        issues.append("resolution_mismatch")
                except ValueError:
                    issues.append("invalid_expected_resolution")

        duration = float(format_info.get("duration") or 0.0)
        max_duration = source.get("max_duration_seconds")
        if max_duration is not None and duration > float(max_duration) + 0.25:
            issues.append("duration_exceeded")

        min_duration = source.get("min_duration_seconds")
        if min_duration is not None and duration < float(min_duration) - 0.25:
            issues.append("duration_too_short")

        captions_ref = str(source.get("captions_ref", "")).strip()
        if cfg.get("require_caption_track", True) and captions_ref:
            captions = Path(captions_ref).expanduser()
            if not captions.is_absolute():
                captions = self.root / captions
            if not captions.resolve().is_file():
                issues.append("captions_missing")

        return MediaQAResult(True, {
            "media_ref": str(path.relative_to(self.root)),
            "duration": duration,
            "size_bytes": int(format_info.get("size", path.stat().st_size)),
            "format": format_info.get("format_name"),
            "video": video,
            "audio": audio,
            "issues": issues,
            "passed": not issues,
        })


__all__ = ["MediaQA", "MediaQAResult"]
