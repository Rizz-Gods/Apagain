import re
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

@dataclass
class BlueprintResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class AutomationDesigner:
    id = "automation-designer"

    def supports(self, capability: str) -> bool:
        return capability == "automation-design"

    @staticmethod
    def _complexity(automation_hits: float) -> str:
        if automation_hits >= 75:
            return "medium"
        if automation_hits >= 55:
            return "low-medium"
        return "low"

    @staticmethod
    def _blueprint(opportunity: dict[str, Any]) -> dict[str, Any]:
        title = re.sub(r"^#+\s*", "", str(opportunity.get("title", ""))).strip()
        snippet = str(opportunity.get("snippet", "")).strip()
        query = str(opportunity.get("query", "")).strip()
        score = opportunity.get("score", {}) or {}
        automation = float(score.get("automation", 0))
        pain = float(score.get("pain", 0))

        combined = f"{title} {snippet} {query}".lower()
        workflow = [
            "capture customer request or trigger",
            "normalize and validate the incoming data",
            "route the work to the correct business action",
            "execute the repetitive step automatically",
            "notify the operator/customer",
            "log the outcome for analytics",
        ]
        stack = ["n8n", "Python", "official APIs", "SQLite/PostgreSQL"]
        if "browser" in combined or "website" in combined:
            stack.append("agent-browser")
        if "whatsapp" in combined:
            stack.append("WhatsApp Business API")
        if "email" in combined:
            stack.append("Gmail/Outlook API")

        problem = snippet or title or "Repeated manual workflow identified"
        automation_text = (
            "Automate the repeated intake → processing → notification loop "
            "with event-driven workflow execution and human approval only for "
            "external or irreversible actions."
        )

        return {
            "title": f"Automation blueprint: {title[:90] or 'Unnamed workflow'}",
            "problem": problem[:500],
            "automation": automation_text,
            "workflow": workflow,
            "stack": stack,
            "estimated_complexity": AutomationDesigner._complexity(automation),
            "pain_score": pain,
            "automation_score": automation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def execute(self, action: str, payload: dict) -> BlueprintResult:
        if action != "design":
            return BlueprintResult(False, {}, f"Unsupported automation-design action: {action}")
        inputs = payload.get("input", {}).get("opportunities", [])
        if not isinstance(inputs, list):
            return BlueprintResult(False, {}, "input.opportunities must be a list")
        blueprints = []
        for opportunity in inputs[:15]:
            blueprint = self._blueprint(opportunity)
            item = dict(opportunity)
            item["blueprint"] = blueprint
            blueprints.append(item)
        return BlueprintResult(True, {
            "blueprints": blueprints,
            "count": len(blueprints),
            "next": [{"capability": "automation-build", "action": "build", "priority": 55}],
        })
