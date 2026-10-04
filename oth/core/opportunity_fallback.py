from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class OpportunityFallbackResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class OpportunityAnalystFallback:
    """Independent deterministic scoring implementation for opportunity-analysis."""

    id = "opportunity-analyst-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "opportunity-analysis"

    @staticmethod
    def _score(signal: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(
            str(signal.get(key, ""))
            for key in ("title", "snippet", "query")
        ).lower()

        groups = {
            "pain": ("problem", "complaint", "slow", "hard", "frustrat", "expensive", "manual"),
            "demand": ("looking for", "alternative", "best", "software", "tool", "service", "review"),
            "automation": ("spreadsheet", "copy", "email", "schedule", "workflow", "repetitive", "data entry"),
            "differentiation": ("niche", "local", "industry", "vertical", "small business"),
        }
        hits = {name: sum(1 for word in words if word in text) for name, words in groups.items()}
        pain = min(100, 30 + hits["pain"] * 12)
        demand = min(100, 30 + hits["demand"] * 10)
        automation = min(100, 20 + hits["automation"] * 14)
        differentiation = min(100, 30 + hits["differentiation"] * 12)

        signal_type = str(signal.get("signal_type", "")).lower()
        if signal_type == "complaint":
            pain = min(100, pain + 10)
        elif signal_type == "friction":
            automation = min(100, automation + 10)
        elif signal_type == "alternative":
            demand = min(100, demand + 10)

        score = (
            pain * 0.35
            + demand * 0.30
            + automation * 0.25
            + differentiation * 0.10
        )
        quality = float(signal.get("quality", 1.0) or 1.0)
        reasons = [f"{name} signals={count}" for name, count in hits.items() if count]
        if not reasons:
            reasons = ["weak initial signal; needs corroboration"]

        return {
            "score": round(min(score * quality, 100), 2),
            "pain": pain,
            "demand": demand,
            "automation": automation,
            "differentiation": differentiation,
            "reasons": reasons,
        }

    def execute(self, action: str, payload: dict[str, Any]) -> OpportunityFallbackResult:
        if action != "score":
            return OpportunityFallbackResult(False, {}, f"Unsupported action: {action}")
        source = payload.get("input", {})
        signals = source.get("signals") or source.get("opportunities") or []
        if not isinstance(signals, list):
            return OpportunityFallbackResult(False, {}, "input.signals/input.opportunities must be a list")
        scored = []
        for signal in signals[:40]:
            item = dict(signal)
            item["score"] = self._score(signal)
            scored.append(item)
        scored.sort(key=lambda item: item["score"]["score"], reverse=True)
        return OpportunityFallbackResult(
            True,
            {
                "opportunities": scored[:20],
                "count": len(scored),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "fallback": True,
                "fallback_reason": "primary_opportunity_analyst_unavailable",
                "next": [{"capability": "automation-design", "action": "design", "priority": 60}],
            },
        )
