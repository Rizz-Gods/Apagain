import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SocialEditorResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class SocialEditorialDirector:
    id = "social-editor"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_editorial.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-editor"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"briefs": [], "revisions": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"briefs": [], "revisions": []}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:70] or "creative"
    def _choose_format(self, platform: str, purpose: str, stage: str,
                       evidence: bool) -> dict[str, Any]:
        p = platform.lower()
        purpose = purpose.lower()
        stage = stage.lower()
        if p == "youtube":
            if purpose in {"awareness", "discovery"}:
                return {"format": "short", "duration_seconds": 35 if evidence else 25}
            if stage in {"consideration", "proof"}:
                return {"format": "short_or_explainer", "duration_seconds": 55}
            return {"format": "demo_video", "duration_seconds": 75}
        if p == "instagram":
            if purpose in {"awareness", "discovery"}:
                return {"format": "reel", "duration_seconds": 25}
            if stage == "proof":
                return {"format": "reel_case_study", "duration_seconds": 40}
            return {"format": "reel_demo", "duration_seconds": 45}
        if p == "linkedin":
            if stage == "proof":
                return {"format": "carousel_or_native_video", "duration_seconds": 50}
            return {"format": "carousel_or_text", "duration_seconds": 0}
        return {"format": "text_or_single_visual", "duration_seconds": 0}

    def _brief(self, campaign: dict[str, Any], platform: str,
               purpose: str, stage: str, sources: list[str]) -> dict[str, Any]:
        market = str(campaign.get("market", ""))
        pain = str(campaign.get("pain", ""))
        proof = str(campaign.get("proof", ""))
        hook = str(campaign.get("hook") or pain)
        evidence = bool(proof.strip())
        fmt = self._choose_format(platform, purpose, stage, evidence)
        audience = campaign.get("audience") or {
            "primary": f"People currently solving {market} problems",
            "signal": "Active pain, comparison, or workflow intent",
        }
        recipe = [
            "Open on the pain in the first 1-2 seconds.",
            "Show one concrete mechanism before making a broad claim.",
            "Cut every sentence that does not move the viewer toward proof or action.",
            "Use captions; assume sound-off viewing first.",
            "End with one low-friction next step, not a generic engagement bait CTA.",
        ]
        if fmt["format"].startswith("reel") or fmt["format"] == "short":
            recipe += [
                "Use 2-4 visual changes before the midpoint.",
                "Put the strongest proof before the final third.",
                "Loop or hard-cut the ending when it improves retention.",
            ]
        source_pack = sources or ["campaign brief", "approved OTH opportunity evidence"]
        return {
            "brief_id": f"brief-{self._slug(campaign.get('campaign_id', market))}-{platform}",
            "campaign_id": campaign.get("campaign_id"),
            "platform": platform,
            "purpose": purpose,
            "funnel_stage": stage,
            "audience": audience,
            "format": fmt["format"],
            "duration_seconds": fmt["duration_seconds"],
            "hook": hook,
            "claim": pain,
            "proof": proof,
            "sources": source_pack,
            "edit_recipe": recipe,
            "visual_plan": [
                "Problem visual",
                "Mechanism / interface / process",
                "Proof or result",
                "Single CTA frame",
            ],
            "audio": {
                "voice": "natural, concise, confident",
                "music": "subordinate to speech",
                "effects": "only where they reinforce a cut or transition",
            },
            "captioning": "burned-in or platform-native captions with readable timing",
            "thumbnail": "One outcome-focused frame with minimal text",
            "status": "ready_for_production",
        }

    def execute(self, action: str, payload: dict) -> SocialEditorResult:
        if action not in {"brief", "plan", "review"}:
            return SocialEditorResult(False, {}, f"Unsupported social-editor action: {action}")

        source = payload.get("input", {})
        data = self._load()
        campaigns = source.get("campaigns") or []
        if action == "review":
            return SocialEditorResult(True, {
                "briefs": data.get("briefs", []),
                "revisions": data.get("revisions", [])[-20:],
            })

        if isinstance(campaigns, dict):
            campaigns = [campaigns]
        if not campaigns:
            campaign = source.get("campaign") or {}
            campaigns = [campaign] if campaign else []

        requested_platforms = source.get("platforms") or [
            "linkedin", "x", "youtube", "instagram"
        ]
        purpose = str(source.get("purpose", "discovery"))
        stage = str(source.get("funnel_stage", "awareness"))
        sources = [str(x) for x in (source.get("sources") or [])]

        briefs = []
        existing = {
            (x.get("campaign_id"), x.get("platform"))
            for x in data.get("briefs", [])
        }
        for campaign in campaigns:
            for platform in requested_platforms:
                key = (campaign.get("campaign_id"), platform)
                if key in existing:
                    continue
                brief = self._brief(campaign, platform, purpose, stage, sources)
                briefs.append(brief)

        data.setdefault("briefs", []).extend(briefs)
        data["last_planned_at"] = datetime.now(timezone.utc).isoformat()
        self._save(data)
        return SocialEditorResult(True, {
            "briefs": briefs,
            "count": len(briefs),
            "next": [
                {
                    "capability": "media-assets",
                    "action": "list",
                    "priority": 61,
                }
            ] if briefs else [],
        })
    def review_draft(self, content: dict[str, Any]) -> dict[str, Any]:
        text = str(content.get("text") or content.get("description") or "")
        issues = []
        if len(text) > 10000:
            issues.append("excessive_length")
        if re.search(r"\b(guaranteed|risk[- ]free|instant riches)\b", text, re.I):
            issues.append("unsupported_absolute_claim")
        if text.count("!") > 4:
            issues.append("over_emphatic")
        return {
            "approved_for_internal_queue": not issues,
            "issues": issues,
            "recommended_action": "revise" if issues else "keep",
        }


__all__ = ["SocialEditorialDirector", "SocialEditorResult"]
