from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class LocalReasoningResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class LocalReasonerWorker:
    """Deterministic planning fallback used when external LLM reasoning is unavailable."""

    id = "reasoning-local"

    def supports(self, capability: str) -> bool:
        return capability == "reasoning"

    @staticmethod
    def _steps(prompt: str) -> list[str]:
        p = prompt.lower()
        steps = []
        if any(x in p for x in ("research", "find", "discover", "market")):
            steps.append("collect evidence and identify the decision-relevant facts")
        if any(x in p for x in ("analy", "compare", "evaluate", "why")):
            steps.append("separate observations, constraints, alternatives, and trade-offs")
        if any(x in p for x in ("build", "create", "implement", "code")):
            steps.append("define the smallest testable implementation and its verification")
        if any(x in p for x in ("debug", "fix", "error", "broken")):
            steps.append("reproduce the failure, isolate the cause, then verify the repair")
        if not steps:
            steps = [
                "extract the objective and constraints",
                "identify the smallest executable next actions",
                "verify the result and record remaining uncertainty",
            ]
        return steps

    def execute(self, action: str, payload: dict[str, Any]) -> LocalReasoningResult:
        if action != "prompt":
            return LocalReasoningResult(False, {}, f"Unsupported local reasoning action: {action}")
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            return LocalReasoningResult(False, {}, "Missing prompt")
        constraints = re.findall(r"(?:must|should|avoid|do not|don't)\s+[^.]{5,120}", prompt, re.I)
        steps = self._steps(prompt)
        output = {
            "response": {
                "mode": "deterministic_fallback",
                "objective": prompt[:1000],
                "steps": steps,
                "constraints": constraints[:10],
                "verification": "re-run the relevant OTH task/evaluation after execution",
            },
            "fallback": True,
            "fallback_reason": "external_reasoning_unavailable",
        }
        return LocalReasoningResult(True, output)


__all__ = ["LocalReasonerWorker", "LocalReasoningResult"]
