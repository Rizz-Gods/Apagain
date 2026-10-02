import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class SocialContentResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialContentEngine:
    id = "social-content"

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]
        self.queue_path = self.root / "data" / "social_queue.json"
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-content"

    def _load(self) -> dict[str, Any]:
        if not self.queue_path.exists():
            return {"items": []}
        return json.loads(self.queue_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.queue_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:70] or "content"
    @staticmethod
    def _compact(text: str, limit: int) -> str:
        text = str(text).strip()
        if len(text) <= limit:
            return text
        if limit <= 3:
            return text[:limit]
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _hashtags(market: str, offer: str) -> list[str]:
        words = re.findall(r"[A-Za-z0-9]+", f"{market} {offer}")
        unique = []
        for word in words:
            tag = f"#{word.lower()}"
            if len(word) >= 4 and tag not in unique:
                unique.append(tag)
        return unique[:6]

    def _draft(self, market: str, offer: str, pain: str, proof: str, cta: str, hook: str, pillar: str) -> dict[str, Any]:
        opening = hook.strip() or pain
        core = f"{pain}. {proof}" if proof else pain
        hashtags = self._hashtags(market, offer)
        return {
            "linkedin": {
                "format": "text_or_carousel",
                "hook": opening,
                "pillar": pillar,
                "text": f"{opening}\n\n{pain}\n\n{proof}\n\n{cta}\n\n{' '.join(hashtags[:4])}".strip(),
                "media_brief": "Carousel: problem -> evidence -> mechanism -> CTA.",
            },
            "x": {
                "format": "text",
                "hook": opening,
                "pillar": pillar,
                "text": f"{opening} {proof} {cta}".strip(),
                "media_brief": "Optional single proof visual.",
            },
            "youtube": {
                "format": "short_or_video",
                "hook": opening,
                "pillar": pillar,
                "title": f"{opening[:70]} | {offer}",
                "description": f"{opening}\n\n{core}\n\n{cta}\n\n{' '.join(hashtags)}",
                "media_brief": "45-90 second explanation with one concrete proof point.",
            },
            "instagram": {
                "format": "reel_or_carousel",
                "hook": opening,
                "pillar": pillar,
                "caption": f"{opening}\n\n{pain}\n\n{proof}\n\n{cta}\n\n{' '.join(hashtags)}".strip(),
                "media_brief": "Reel hook in first 2 seconds; alternative carousel with 5-7 frames.",
            },
        }

    @staticmethod
    def _qa(package: dict[str, Any]) -> dict[str, Any]:
        limits = {"linkedin": 3000, "x": 280, "youtube": 5000, "instagram": 2200}
        errors = []
        warnings = []
        for platform, payload in package.get("variants", {}).items():
            if platform not in limits:
                errors.append(f"unsupported_platform:{platform}")
                continue
            text = str(
                payload.get("text")
                or payload.get("caption")
                or payload.get("description")
                or ""
            ).strip()
            if not text:
                errors.append(f"{platform}:empty_text")
            elif len(text) > limits[platform]:
                errors.append(f"{platform}:text_limit_exceeded")
            if platform == "youtube" and not str(payload.get("title", "")).strip():
                errors.append("youtube:missing_title")
            if "buy now" in text.lower() or "guaranteed" in text.lower():
                warnings.append(f"{platform}:claim_review_required")
        status = "failed" if errors else "passed"
        return {"status": status, "errors": errors, "warnings": warnings}

    def _queue(self, package: dict[str, Any], platform: str) -> dict[str, Any]:
        data = self._load()
        campaign_id = str(package.get("campaign_id", "")).strip()
        existing = next((
            item for item in data["items"]
            if campaign_id
            and item.get("campaign_id") == campaign_id
            and item.get("platform") == platform
        ), None)
        if existing:
            return existing
        item = {
            "id": f"{self._slug(package['market'])}-{platform}-{len(data['items']) + 1}",
            "content_id": f"{self._slug(package['market'])}-{platform}-{len(data['items']) + 1}",
            "campaign_id": campaign_id,
            "platform": platform,
            "market": package["market"],
            "offer": package["offer"],
            "payload": package["variants"][platform],
            "status": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "due_at": package.get("due_at"),
            "approval": {"required": True, "status": "pending"},
        }
        data["items"].append(item)
        self._save(data)
        return item
    def execute(self, action: str, payload: dict) -> SocialContentResult:
        source = payload.get("input", {})
        if action not in {"draft", "queue", "list"}:
            return SocialContentResult(False, {}, f"Unsupported social-content action: {action}")

        if action == "list":
            return SocialContentResult(True, {"items": self._load()["items"]})

        market = str(source.get("market", "target market")).strip()
        offer = str(source.get("offer", "offer")).strip()
        campaign_id = str(source.get("campaign_id", "")).strip()
        pain = str(source.get("pain", "Manual work is consuming time that should be spent growing the business.")).strip()
        proof = str(source.get("proof", "Show one concrete before/after result or measurable operational improvement.")).strip()
        cta = str(source.get("cta", f"Reply with your workflow and I'll map the first automation worth building.")).strip()
        hook = str(source.get("hook", "")).strip() or pain
        pillar = str(source.get("pillar", "acquisition")).strip() or "acquisition"
        platforms = source.get("platforms") or ["linkedin", "x", "youtube", "instagram"]
        auto_compact = bool(source.get("auto_compact", False))
        variants = self._draft(market, offer, pain, proof, cta, hook, pillar)
        variants = {name: variants[name] for name in platforms if name in variants}
        if auto_compact and "x" in variants:
            variants["x"]["text"] = self._compact(variants["x"]["text"], 280)
        if "youtube" in variants:
            variants["youtube"]["media_ref"] = source.get("media_ref")
            variants["youtube"]["privacy_status"] = source.get("privacy_status", "private")
        if "instagram" in variants:
            variants["instagram"]["media_ref"] = source.get("media_ref")
        package = {
            "version": 1,
            "campaign_id": campaign_id,
            "market": market,
            "offer": offer,
            "pain": pain,
            "proof": proof,
            "cta": cta,
            "hook": hook,
            "pillar": pillar,
            "variants": variants,
            "claim_check": {"required": True, "status": "pending"},
            "due_at": source.get("due_at"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        package["qa"] = self._qa(package)
        queued = []
        if action == "queue":
            if package["qa"]["status"] == "failed":
                return SocialContentResult(False, {"package": package}, "Content QA failed")
            queued = [self._queue(package, platform) for platform in variants]
        return SocialContentResult(True, {
            "package": package,
            "queued": queued,
            "next": [] if action == "draft" else [{
                "capability": "social-actions",
                "action": "doctor",
                "priority": 74,
            }],
        })
