import hashlib
import json
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class MediaResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class MediaAssetManager:
    id = "media-assets"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.config = self._read_json(self.root / "config" / "media.json", {})
        self.registry_path = self.root / "data" / "media_assets.json"
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.media_root = self.root / "data" / "media"
        self.media_root.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "media-assets"

    @staticmethod
    def _read_json(path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _load(self):
        return self._read_json(self.registry_path, {"assets": []})

    def _save(self, data):
        self.registry_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _resolve_input(self, ref: str) -> Path:
        path = Path(str(ref)).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("media_ref must resolve inside the OTH workspace")
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return path

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _probe(self, path: Path):
        ffprobe = Path(self.config.get("ffprobe", "ffprobe"))
        command = [
            str(ffprobe),
            "-v", "error",
            "-show_entries", "format=format_name,duration,size",
            "-show_streams",
            "-of", "json",
            str(path),
        ]
        proc = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "ffprobe failed")
        return json.loads(proc.stdout or "{}")
    def _register(self, source: Path, metadata: dict[str, Any], sha256: str):
        data = self._load()
        existing = next((a for a in data["assets"] if a.get("sha256") == sha256), None)
        if existing:
            existing["last_seen_at"] = self._now()
            self._save(data)
            return existing
        media_id = f"media-{uuid.uuid4().hex[:12]}"
        asset = {
            "media_id": media_id,
            "source_path": str(source),
            "sha256": sha256,
            "filename": source.name,
            "size_bytes": source.stat().st_size,
            "metadata": metadata,
            "status": "ready",
            "created_at": self._now(),
            "last_seen_at": self._now(),
        }
        data["assets"].append(asset)
        self._save(data)
        return asset

    def _normalize_video(self, source: Path, media_id: str):
        ffmpeg = Path(self.config.get("ffmpeg", "ffmpeg"))
        target = self.media_root / f"{media_id}.mp4"
        command = [
            str(ffmpeg), "-y",
            "-i", str(source),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(target),
        ]
        proc = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[-2000:] or "ffmpeg normalization failed")
        return target

    def execute(self, action: str, payload: dict) -> MediaResult:
        source = payload.get("input", {})
        if action == "list":
            return MediaResult(True, {"assets": self._load()["assets"]})

        if action == "inspect":
            try:
                path = self._resolve_input(str(source.get("media_ref", "")))
                metadata = self._probe(path)
                return MediaResult(True, {
                    "path": str(path),
                    "metadata": metadata,
                    "sha256": self._sha256(path),
                })
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                return MediaResult(False, {}, str(exc))

        if action == "register":
            try:
                path = self._resolve_input(str(source.get("media_ref", "")))
                metadata = self._probe(path)
                asset = self._register(path, metadata, self._sha256(path))
                return MediaResult(True, {"asset": asset})
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                return MediaResult(False, {}, str(exc))

        if action == "normalize":
            try:
                path = self._resolve_input(str(source.get("media_ref", "")))
                metadata = self._probe(path)
                sha256 = self._sha256(path)
                asset = self._register(path, metadata, sha256)
                media_id = asset["media_id"]
                if str(metadata.get("format", "")).lower().find("mp4") >= 0:
                    output = path
                else:
                    output = self._normalize_video(path, media_id)
                asset["normalized_path"] = str(output)
                asset["status"] = "ready"
                data = self._load()
                for row in data["assets"]:
                    if row.get("media_id") == media_id:
                        row.update(asset)
                self._save(data)
                return MediaResult(True, {
                    "asset": asset,
                    "media_ref": str(output.relative_to(self.root)),
                })
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                return MediaResult(False, {}, str(exc))

        return MediaResult(False, {}, f"Unsupported media-assets action: {action}")
