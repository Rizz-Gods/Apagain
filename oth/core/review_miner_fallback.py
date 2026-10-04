from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class ReviewMiningFallbackResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class ReviewMinerFallback:
    """Evidence-only review miner; works from already collected signals without browsing."""

    id = "review-miner-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "review-mining"

    @staticmethod
    def _name(signal: dict[str, Any]) -> str:
        title = str(signal.get("title", "")).strip()
        title = re.sub(r"^#+\s*", "", title)
        title = re.sub(r"\b(best|free|online|software|platform|app|tool|reviews?)\b", "", title, flags=re.I)
        return re.sub(r"\s+", " ", title).strip()[:100]

    @staticmethod
    def _quality(signal: dict[str, Any]) -> float:
        hay = " ".join(
            str(signal.get(key, ""))
            for key in ("title", "snippet", "query")
        ).lower()
        hits = sum(
            1
            for word in (
                "complaint", "problem", "issue", "expensive", "slow",
                "missing", "difficult", "frustrat", "alternative",
                "negative", "review", "rating",
            )
            if word in hay
        )
        base = min(1.0, 0.35 + hits * 0.1)
        return round(base * float(signal.get("quality", 1.0) or 1.0), 3)

    def execute(self, action: str, payload: dict[str, Any]) -> ReviewMiningFallbackResult:
        if action != "mine":
            return ReviewMiningFallbackResult(False, {}, f"Unsupported review-mining action: {action}")
        candidates = payload.get("input", {}).get("signals", [])
        if not isinstance(candidates, list):
            return ReviewMiningFallbackResult(False, {}, "input.signals must be a list")

        signals = []
        seen = set()
        for source in candidates[:12]:
            candidate = self._name(source)
            if not candidate:
                continue
            quality = self._quality(source)
            signal = {
                "source": "review-evidence",
                "query": str(source.get("query", "")),
                "title": source.get("title", ""),
                "url": source.get("url", ""),
                "snippet": source.get("snippet", ""),
                "signal_type": "review",
                "quality": quality,
                "candidate": candidate,
                "candidate_url": source.get("url"),
                "raw": source.get("raw", ""),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
            key = (signal["url"], candidate)
            if key in seen:
                continue
            seen.add(key)
            signals.append(signal)

        return ReviewMiningFallbackResult(
            True,
            {
                "signals": signals[:30],
                "count": len(signals),
                "candidates_scanned": min(len(candidates), 12),
                "fallback": True,
                "fallback_reason": "browser_review_mining_unavailable",
                "next": [{"capability": "opportunity-analysis", "action": "score", "priority": 65}],
            },
        )
