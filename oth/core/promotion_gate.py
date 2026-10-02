from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class PromotionResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class PromotionGate:
    id = "promotion-gate"

    def supports(self, capability: str) -> bool:
        return capability == "promotion-gate"

    def execute(self, action: str, payload: dict) -> PromotionResult:
        if action != "promote":
            return PromotionResult(False, {}, f"Unsupported promotion-gate action: {action}")
        results = payload.get("input", {}).get("results", [])
        if not isinstance(results, list):
            return PromotionResult(False, {}, "input.results must be a list")

        decisions = []
        for result in results[:20]:
            qa_status = str(result.get("status", "failed"))
            project_path = str(result.get("project_path", ""))
            opp = result.get("opportunity", {}) or {}
            if qa_status == "passed":
                status = "ready"
                reason = "QA passed; eligible for promotion"
            elif qa_status == "warnings":
                status = "held"
                reason = "QA warnings require dependency resolution or operator review"
            else:
                status = "rejected"
                reason = "QA failed; promotion blocked"

            decisions.append({
                "project_path": project_path,
                "opportunity": opp,
                "status": status,
                "reason": reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        return PromotionResult(True, {
            "decisions": decisions,
            "count": len(decisions),
        })
