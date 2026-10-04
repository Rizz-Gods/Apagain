from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import now_iso


@dataclass(frozen=True)
class LaneCandidate:
    lane: int
    capability: str
    action: str
    worker_id: str


class LaneRouter:
    """Builds an ordered execution lane set without changing task semantics."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "config" / "lanes.json"
        self.config = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"max_lanes": 4, "fallbacks": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {"max_lanes": 4, "fallbacks": {}}
        except (OSError, ValueError):
            return {"max_lanes": 4, "fallbacks": {}}

    @property
    def max_lanes(self) -> int:
        return max(1, min(int(self.config.get("max_lanes", 4)), 4))

    @property
    def circuit_failure_threshold(self) -> int:
        cfg = self.config.get("circuit_breaker", {}) or {}
        return max(1, int(cfg.get("failure_threshold", 3)))

    @property
    def circuit_window(self) -> int:
        cfg = self.config.get("circuit_breaker", {}) or {}
        return max(1, int(cfg.get("window", 12)))

    def candidates(
        self,
        kernel,
        capability: str,
        action: str,
        excluded_workers: set[str] | None = None,
    ) -> list[LaneCandidate]:
        excluded_workers = excluded_workers or set()
        candidates: list[LaneCandidate] = []
        seen: set[str] = set()

        def add_for_capability(
            target_capability: str,
            target_action: str,
            include_excluded: bool,
        ) -> None:
            capability_contract = kernel.workforce.capability_for(target_capability)
            runtime_workers = list(getattr(kernel, "workers", []))

            def priority(worker) -> tuple[float, int]:
                worker_id = getattr(worker, "id", "builtin")
                configured = kernel.workforce.workers.get(worker_id, {}) or {}
                metadata = configured.get("metadata", {}) or {}
                priority_value = int(
                    metadata.get(
                        "priority",
                        getattr(getattr(worker, "agent", None), "metadata", {}).get("priority", 50),
                    )
                )
                health = kernel.db.agent_health(worker_id)
                reliability = float(health.get("reliability", 1.0))
                quality = float(health.get("quality", 1.0))
                return (
                    priority_value
                    + reliability * 10.0
                    + quality * 5.0,
                    priority_value,
                )

            for worker in sorted(runtime_workers, key=priority, reverse=True):
                worker_id = getattr(worker, "id", "builtin")
                if worker_id in seen:
                    continue
                if not include_excluded and worker_id in excluded_workers:
                    continue
                circuit = kernel.db.worker_circuit_state(
                    worker_id,
                    self.circuit_failure_threshold,
                    self.circuit_window,
                )
                if circuit["open"] and not include_excluded:
                    continue
                try:
                    if not worker.supports(target_capability):
                        continue
                except Exception:
                    continue

                configured = worker_id in kernel.workforce.workers
                if configured:
                    contract = kernel.workforce.contract_for(worker_id)
                    if any(
                        permission not in contract.permissions
                        for permission in capability_contract.required_permissions
                    ):
                        continue

                seen.add(worker_id)
                candidates.append(
                    LaneCandidate(
                        lane=len(candidates) + 1,
                        capability=target_capability,
                        action=target_action,
                        worker_id=worker_id,
                    )
                )
                if len(candidates) >= self.max_lanes:
                    return

        add_for_capability(capability, action, False)

        for spec in self.config.get("fallbacks", {}).get(capability, []):
            if len(candidates) >= self.max_lanes:
                break
            spec = spec if isinstance(spec, dict) else {}
            fallback_cap = str(spec.get("capability", "")).strip()
            fallback_action = str(spec.get("action", action)).strip()
            if not fallback_cap:
                continue
            add_for_capability(fallback_cap, fallback_action, False)

        # After a complete lane cycle fails, permit a fresh recovery cycle
        # rather than deadlocking the task forever behind its quarantine set.
        if not candidates:
            seen.clear()
            add_for_capability(capability, action, True)
            for spec in self.config.get("fallbacks", {}).get(capability, []):
                if len(candidates) >= self.max_lanes:
                    break
                spec = spec if isinstance(spec, dict) else {}
                fallback_cap = str(spec.get("capability", "")).strip()
                fallback_action = str(spec.get("action", action)).strip()
                if fallback_cap:
                    add_for_capability(fallback_cap, fallback_action, True)

        return candidates[: self.max_lanes]

    def record_failure(self, kernel, task_id: str, candidate: LaneCandidate, error: str | None) -> None:
        kernel.db.add_event(
            task_id,
            f"lane.{candidate.lane}.failed",
            {
                "lane": candidate.lane,
                "capability": candidate.capability,
                "action": candidate.action,
                "worker_id": candidate.worker_id,
                "error": error,
            },
            now_iso(),
        )

    def record_success(self, kernel, task_id: str, candidate: LaneCandidate) -> None:
        kernel.db.add_event(
            task_id,
            f"lane.{candidate.lane}.succeeded",
            {
                "lane": candidate.lane,
                "capability": candidate.capability,
                "action": candidate.action,
                "worker_id": candidate.worker_id,
            },
            now_iso(),
        )
