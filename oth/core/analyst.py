import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

@dataclass
class AnalysisResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class OpportunityAnalyst:
    id = "opportunity-analyst"

    def supports(self, capability: str) -> bool:
        return capability == "opportunity-analysis"

    @staticmethod
    def _score(signal: dict) -> dict:
        text = f'{signal.get("title","")} {signal.get("snippet","")} {signal.get("query","")}'.lower()
        pain_words = ("problem", "issue", "hard", "slow", "manual", "expensive", "sucks",
                      "frustrat", "complaint", "difficult", "time-consuming")
        demand_words = ("alternative", "best", "how to", "software", "tool", "service",
                        "template", "review", "compare")
        automation_words = ("manual", "spreadsheet", "copy", "email", "schedule",
                            "report", "data entry", "workflow", "repetitive")
        diff_words = ("niche", "specific", "for small", "industry", "local", "vertical")

        pain_hits = sum(1 for w in pain_words if w in text)
        demand_hits = sum(1 for w in demand_words if w in text)
        automation_hits = sum(1 for w in automation_words if w in text)
        diff_hits = sum(1 for w in diff_words if w in text)

        pain = min(100, 35 + pain_hits * 10)
        demand = min(100, 30 + demand_hits * 10)
        automation = min(100, 20 + automation_hits * 15)
        differentiation = min(100, 30 + diff_hits * 15)

        if signal.get("signal_type") == "complaint":
            pain += 10
        if signal.get("signal_type") == "alternative":
            demand += 10
        if signal.get("signal_type") == "friction":
            automation += 10

        base_score = (
            pain * 0.35 + demand * 0.30 + automation * 0.25 + differentiation * 0.10
        )
        quality = float(signal.get("quality", 1.0))
        score = round(base_score * quality, 2)
        reasons = []
        if pain_hits: reasons.append("pain language detected")
        if demand_hits: reasons.append("active demand/comparison language detected")
        if automation_hits: reasons.append("automation opportunity language detected")
        if diff_hits: reasons.append("potential niche/differentiation signal")
        if not reasons: reasons.append("weak initial signal; needs corroboration")

        return {
            "score": min(score, 100),
            "pain": min(pain, 100),
            "demand": min(demand, 100),
            "automation": min(automation, 100),
            "differentiation": min(differentiation, 100),
            "reasons": reasons,
        }

    def execute(self, action: str, payload: dict) -> AnalysisResult:
        if action != "score":
            return AnalysisResult(False, {}, f"Unsupported action: {action}")
        source = payload.get("input", {})
        signals = source.get("signals") or source.get("opportunities") or []
        if not isinstance(signals, list):
            return AnalysisResult(False, {}, "input.signals/input.opportunities must be a list")
        scored = []
        for signal in signals[:40]:
            item = dict(signal)
            item["score"] = self._score(signal)
            scored.append(item)
        scored.sort(key=lambda x: x["score"]["score"], reverse=True)
        return AnalysisResult(True, {
            "opportunities": scored[:20],
            "count": len(scored),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "next": [{"capability": "automation-design", "action": "design", "priority": 60}],
        })
