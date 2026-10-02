import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class MediaIngestResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class MediaIngest:
    id = "media-ingest"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.dir = self.root / "data" / "media" / "ingest"
        self.registry = self.root / "data" / "media_sources.json"
        self.dir.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "media-ingest"

    def _load(self):
        if not self.registry.exists():
            return {"sources": []}
        try:
            return json.loads(self.registry.read_text(encoding="utf-8"))
        except Exception:
            return {"sources": []}

    def _save(self, data):
        self.registry.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def execute(self, action: str, payload: dict) -> MediaIngestResult:
        if action == "list":
            return MediaIngestResult(True, {"sources": self._load()["sources"]})
        if action != "download":
            return MediaIngestResult(False, {}, f"Unsupported media-ingest action: {action}")

        source = payload.get("input", {})
        url = str(source.get("url", "")).strip()
        if not url:
            return MediaIngestResult(False, {}, "url is required")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "yt_dlp",
                 "--no-playlist",
                 "--restrict-filenames",
                 "--write-info-json",
                 "--write-thumbnail",
                 "-o", str(self.dir / "%(id)s.%(ext)s"),
                 url],
                capture_output=True,
                text=True,
                timeout=int(source.get("timeout_seconds", 900)),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return MediaIngestResult(False, {}, "yt-dlp timed out", retryable=True)
        if proc.returncode != 0:
            return MediaIngestResult(False, {}, proc.stderr[-2000:], retryable=True)

        rows = []
        for info_path in self.dir.glob("*.info.json"):
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            row = {
                "source_id": str(info.get("id") or info_path.stem),
                "url": info.get("webpage_url") or url,
                "title": info.get("title"),
                "uploader": info.get("uploader"),
                "duration": info.get("duration"),
                "path": str(info_path),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(row)

        data = self._load()
        existing = {x.get("source_id") for x in data["sources"]}
        for row in rows:
            if row["source_id"] not in existing:
                data["sources"].append(row)
        self._save(data)
        return MediaIngestResult(True, {"sources": rows, "count": len(rows)})


__all__ = ["MediaIngest", "MediaIngestResult"]
