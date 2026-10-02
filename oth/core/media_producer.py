import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class MediaProducerResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class MediaProducer:
    id = "media-producer"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "production_manifests.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "media-production"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"manifests": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"manifests": []}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80] or "production"

    def _platform_template(self, platform: str, brief: dict[str, Any]) -> dict[str, Any]:
        fmt = str(brief.get("format", "")).lower()
        if platform == "youtube":
            return {
                "aspect_ratio": "9:16" if "short" in fmt else "16:9",
                "duration_seconds": int(brief.get("duration_seconds") or 45),
                "hook_window_seconds": 2,
                "cut_density": "high",
                "captions": "word_or_phrase_timed",
                "thumbnail": "outcome_first",
            }
        if platform == "instagram":
            return {
                "aspect_ratio": "9:16",
                "duration_seconds": int(brief.get("duration_seconds") or 25),
                "hook_window_seconds": 2,
                "cut_density": "high",
                "captions": "word_or_phrase_timed",
                "thumbnail": "reel_cover",
            }
        if platform == "linkedin":
            return {
                "aspect_ratio": "9:16",
                "duration_seconds": int(brief.get("duration_seconds") or 45),
                "hook_window_seconds": 3,
                "cut_density": "medium",
                "captions": "sentence_timed",
                "thumbnail": "professional_proof",
            }
        return {
            "aspect_ratio": "1:1",
            "duration_seconds": 25,
            "hook_window_seconds": 2,
            "cut_density": "high",
            "captions": "sentence_timed",
            "thumbnail": "minimal",
        }

    def _timeline(self, brief: dict[str, Any], template: dict[str, Any]) -> list[dict[str, Any]]:
        duration = max(int(template["duration_seconds"]), 5)
        hook = min(template["hook_window_seconds"], duration)
        proof_start = max(hook + 4, int(duration * 0.45))
        return [
            {"id": "hook", "start": 0, "end": hook, "purpose": "pattern_interrupt_and_pain"},
            {"id": "context", "start": hook, "end": min(proof_start, duration),
             "purpose": "why_the_problem_matters"},
            {"id": "proof", "start": min(proof_start, duration), "end": max(min(proof_start + int(duration * 0.30), duration - 3), min(proof_start, duration)),
             "purpose": "show_mechanism_or_evidence"},
            {"id": "cta", "start": max(duration - 3, 0), "end": duration,
             "purpose": "single_low_friction_next_step"},
        ]
    def _assets(self, brief: dict[str, Any]) -> list[dict[str, Any]]:
        sources = brief.get("sources") or []
        return [{
            "role": "source",
            "ref": str(source),
            "required": True,
        } for source in sources]

    def _render(self, platform: str, template: dict[str, Any]) -> dict[str, Any]:
        profile = {
            "youtube": "youtube_short",
            "instagram": "instagram_reel",
            "linkedin": "linkedin_native_video",
            "x": "social_master",
        }.get(platform, "social_master")
        return {
            "profile": profile,
            "resolution": "1080x1920" if template["aspect_ratio"] == "9:16" else "1920x1080",
            "frame_rate": 30,
            "audio_sample_rate": 48000,
            "codec": "h264",
            "container": "mp4",
            "fast_start": True,
            "captions_burned": True,
        }

    def execute(self, action: str, payload: dict) -> MediaProducerResult:
        if action not in {"plan", "list", "review"}:
            return MediaProducerResult(False, {}, f"Unsupported media-production action: {action}")

        data = self._load()
        if action == "list":
            return MediaProducerResult(True, {"manifests": data.get("manifests", [])})

        if action == "review":
            return MediaProducerResult(True, {"manifests": data.get("manifests", [])[-20:]})

        source = payload.get("input", {})
        briefs = source.get("briefs") or []
        if isinstance(briefs, dict):
            briefs = [briefs]
        created = []

        existing = {
            x.get("brief_id") for x in data.get("manifests", [])
        }
        for brief in briefs:
            brief_id = brief.get("brief_id")
            if brief_id in existing:
                continue
            platform = str(brief.get("platform", "")).lower()
            template = self._platform_template(platform, brief)
            timeline = self._timeline(brief, template)
            manifest = {
                "manifest_id": f"prod-{self._slug(str(brief_id or platform))}",
                "brief_id": brief_id,
                "campaign_id": brief.get("campaign_id"),
                "platform": platform,
                "purpose": brief.get("purpose"),
                "funnel_stage": brief.get("funnel_stage"),
                "audience": brief.get("audience"),
                "format": brief.get("format"),
                "template": template,
                "timeline": timeline,
                "assets": self._assets(brief),
                "hook": brief.get("hook"),
                "claim": brief.get("claim"),
                "proof": brief.get("proof"),
                "edit_recipe": brief.get("edit_recipe", []),
                "audio": brief.get("audio", {}),
                "captioning": brief.get("captioning"),
                "thumbnail": brief.get("thumbnail"),
                "render": self._render(platform, template),
                "status": "ready_for_resolve",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            data["manifests"].append(manifest)
            created.append(manifest)

        self._save(data)
        return MediaProducerResult(True, {
            "manifests": created,
            "count": len(created),
            "next": [{
                "capability": "resolve-bridge",
                "action": "prepare_project",
                "priority": 68,
                "payload": {"input": {"manifests": created}},
            }] if created else [],
        })
__all__ = ["MediaProducer", "MediaProducerResult"]
