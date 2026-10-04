from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Evaluation:
    quality: float
    success: bool
    lane: int
    worker_id: str
    observations: dict[str, Any]
    lesson: str


class ExecutionEvaluator:
    """Operational evaluator for routing quality, not subjective content quality."""

    def evaluate(
        self,
        *,
        success: bool,
        result_output: dict[str, Any] | None,
        error: str | None,
        lane_history: list[dict[str, Any]],
    ) -> Evaluation:
        output = result_output or {}
        lane = int(lane_history[-1].get("lane", 0)) if lane_history else 0
        worker_id = str(lane_history[-1].get("worker_id", "unknown")) if lane_history else "unknown"

        output_signal = min(len(output.keys()) / 5.0, 1.0)
        lane_efficiency = 1.0 / max(lane, 1) if lane else 0.0
        quality = (
            0.60 * (1.0 if success else 0.0)
            + 0.25 * lane_efficiency
            + 0.15 * output_signal
        )
        fallback = bool(output.get("fallback"))
        if fallback:
            quality *= 0.70
        quality = round(max(0.0, min(1.0, quality)), 4)

        if success and fallback:
            lesson = "fallback lane completed the task with reduced capability"
        elif success and lane == 1:
            lesson = "primary lane completed cleanly"
        elif success:
            lesson = f"lane {lane} recovered the task after earlier lane failure"
        else:
            lesson = "all available execution lanes failed; recovery or operator attention required"

        verification = output.get("verification")
        if isinstance(verification, dict) and "passed" in verification:
            verification_passed = bool(verification["passed"])
        elif isinstance(verification, dict) and "returncode" in verification:
            verification_passed = int(verification["returncode"]) == 0
        else:
            verification_passed = None
        observations = {
            "lane_count": len(lane_history),
            "failed_lanes": sum(1 for item in lane_history if not item.get("success")),
            "output_keys": sorted(output.keys()),
            "error": error,
            "provider": output.get("provider"),
            "model": output.get("model"),
            "tier": output.get("tier"),
            "complexity": output.get("complexity"),
            "attempts": output.get("attempts"),
            "implementation_changed": output.get("implementation_changed"),
            "implementation_expected": output.get("implementation_expected"),
            "verification_passed": verification_passed,
        }
        return Evaluation(
            quality=quality,
            success=success,
            lane=lane,
            worker_id=worker_id,
            observations=observations,
            lesson=lesson,
        )
