from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class BlueprintFallbackResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class AutomationDesignerFallback:
    """Independent blueprint generator preserving the primary designer contract."""

    id = "automation-designer-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "automation-design"

    @staticmethod
    def _blueprint(opportunity: dict[str, Any]) -> dict[str, Any]:
        title = str(opportunity.get("title", "")).strip() or "Unnamed workflow"
        snippet = str(opportunity.get("snippet", "")).strip()
        score = opportunity.get("score", {}) or {}
        automation = float(score.get("automation", 0) or 0)
        pain = float(score.get("pain", 0) or 0)
        workflow = [
            "capture trigger and input",
            "validate and normalize data",
            "execute deterministic processing",
            "request approval for irreversible external actions",
            "notify the relevant party",
            "record outcome and metrics",
        ]
        return {
            "title": f"Automation blueprint: {title[:90]}",
            "problem": (snippet or title)[:500],
            "automation": "Replace repetitive intake-to-notification work with a policy-gated event workflow.",
            "workflow": workflow,
            "stack": ["Python", "Node-RED", "official APIs", "SQLite/PostgreSQL"],
            "estimated_complexity": "medium" if automation >= 70 else "low-medium",
            "pain_score": pain,
            "automation_score": automation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def execute(self, action: str, payload: dict[str, Any]) -> BlueprintFallbackResult:
        if action != "design":
            return BlueprintFallbackResult(False, {}, f"Unsupported automation-design fallback action: {action}")
        opportunities = payload.get("input", {}).get("opportunities", [])
        if not isinstance(opportunities, list):
            return BlueprintFallbackResult(False, {}, "input.opportunities must be a list")
        blueprints = []
        for opportunity in opportunities[:15]:
            item = dict(opportunity)
            item["blueprint"] = self._blueprint(opportunity)
            blueprints.append(item)
        return BlueprintFallbackResult(
            True,
            {
                "blueprints": blueprints,
                "count": len(blueprints),
                "fallback": True,
                "fallback_reason": "primary_automation_designer_unavailable",
                "next": [{"capability": "automation-build", "action": "build", "priority": 55}],
            },
        )
