from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retryable: bool = True


@dataclass(frozen=True)
class EscalationPolicy:
    on: tuple[str, ...] = ("approval_required", "repeated_failure", "no_worker")
    target: str = "pilot"


@dataclass(frozen=True)
class WorkerContract:
    worker_id: str
    department: str = "ops"
    objective: str = "Execute assigned OTH work safely and return structured results."
    permissions: tuple[str, ...] = ("read", "local_execute")
    capability_grants: dict[str, tuple[str, ...]] = field(default_factory=dict)
    memory_scope: str = "task"
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    escalation: EscalationPolicy = field(default_factory=EscalationPolicy)
    metrics: tuple[str, ...] = ("success_rate", "reliability", "latency")


@dataclass(frozen=True)
class CapabilityContract:
    capability: str
    department: str
    risk: str = "safe"
    required_permissions: tuple[str, ...] = ()
    objective: str = ""


@dataclass(frozen=True)
class WorkerView:
    worker_id: str
    name: str
    status: str
    capabilities: tuple[str, ...]
    contract: WorkerContract


class WorkforceRegistry:
    """Policy-aware control plane over the existing agent registry."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.agents_path = self.root / "config" / "agents.json"
        self.workforce_path = self.root / "config" / "workforce.json"
        self._load()

    def _read_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return default
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else default
        except (OSError, ValueError):
            return default

    def _load(self) -> None:
        agent_config = self._read_json(self.agents_path, {"agents": []})
        workforce_config = self._read_json(self.workforce_path, {})
        self.defaults = workforce_config.get("defaults", {}) or {}
        self.worker_overrides = workforce_config.get("workers", {}) or {}
        self.capability_overrides = workforce_config.get("capabilities", {}) or {}
        self.workers: dict[str, dict[str, Any]] = {}
        for agent in agent_config.get("agents", []):
            if not isinstance(agent, dict) or not agent.get("id"):
                continue
            self.workers[agent["id"]] = agent

    @staticmethod
    def _tuple(value: Any, fallback: tuple[str, ...] = ()) -> tuple[str, ...]:
        if value is None:
            return fallback
        if isinstance(value, (list, tuple)):
            return tuple(str(x) for x in value)
        return (str(value),)

    def contract_for(self, worker_id: str) -> WorkerContract:
        override = self.worker_overrides.get(worker_id, {}) or {}
        retry_raw = dict(self.defaults.get("retry", {}) or {})
        retry_raw.update(override.get("retry", {}) or {})
        escalation_raw = dict(self.defaults.get("escalation", {}) or {})
        escalation_raw.update(override.get("escalation", {}) or {})
        grants_raw = override.get("capability_grants", {}) or {}
        capability_grants = {
            str(capability): self._tuple(permissions)
            for capability, permissions in grants_raw.items()
        }
        return WorkerContract(
            worker_id=worker_id,
            department=str(
                override.get("department")
                or self.workers.get(worker_id, {}).get("metadata", {}).get("department")
                or self.defaults.get("department", "ops")
            ),
            objective=str(
                override.get("objective")
                or self.workers.get(worker_id, {}).get("metadata", {}).get("objective")
                or self.defaults.get("objective", "Execute assigned OTH work safely and return structured results.")
            ),
            permissions=self._tuple(
                override.get("permissions"),
                self._tuple(self.defaults.get("permissions"), ("read", "local_execute")),
            ),
            capability_grants=capability_grants,
            memory_scope=str(
                override.get("memory_scope")
                or self.defaults.get("memory_scope", "task")
            ),
            retry=RetryPolicy(
                max_attempts=max(int(retry_raw.get("max_attempts", 1)), 0),
                retryable=bool(retry_raw.get("retryable", True)),
            ),
            escalation=EscalationPolicy(
                on=self._tuple(
                    escalation_raw.get("on"),
                    ("approval_required", "repeated_failure", "no_worker"),
                ),
                target=str(escalation_raw.get("target", "pilot")),
            ),
            metrics=self._tuple(
                override.get("metrics"),
                self._tuple(
                    self.defaults.get("metrics"),
                    ("success_rate", "reliability", "latency"),
                ),
            ),
        )

    def capability_for(self, capability: str) -> CapabilityContract:
        override = self.capability_overrides.get(capability, {}) or {}
        worker = next(
            (agent for agent in self.workers.values() if capability in agent.get("capabilities", [])),
            {},
        )
        return CapabilityContract(
            capability=capability,
            department=str(
                override.get("department")
                or worker.get("metadata", {}).get("department")
                or "ops"
            ),
            risk=str(override.get("risk", "safe")),
            required_permissions=self._tuple(override.get("required_permissions")),
            objective=str(
                override.get("objective")
                or f"Execute {capability} work within OTH policy."
            ),
        )

    def list_workers(self, db=None) -> list[WorkerView]:
        views = []
        for worker_id, agent in self.workers.items():
            views.append(
                WorkerView(
                    worker_id=worker_id,
                    name=str(agent.get("name", worker_id)),
                    status=str(agent.get("status", "offline")),
                    capabilities=tuple(agent.get("capabilities", [])),
                    contract=self.contract_for(worker_id),
                )
            )
        return views

    def resolve_candidates(self, capability: str, db=None, action: str | None = None) -> list[WorkerView]:
        cap = self.capability_for(capability)
        candidates = []
        for view in self.list_workers(db):
            if capability not in view.capabilities:
                continue
            if view.status not in {"available", "online", "ready"}:
                continue
            if any(permission not in view.contract.permissions for permission in cap.required_permissions):
                continue
            candidates.append(view)

        def score(view: WorkerView) -> tuple[float, int]:
            reliability = 1.0
            if db is not None:
                reliability = float(db.agent_health(view.worker_id).get("reliability", 1.0))
            metadata = self.workers[view.worker_id].get("metadata", {})
            priority = int(metadata.get("priority", 50))
            return (priority + reliability * 10.0, priority)

        candidates.sort(key=score, reverse=True)
        return candidates

    def coverage(self, db=None) -> dict[str, Any]:
        lane_config = {}
        lanes_path = self.root / "config" / "lanes.json"
        if lanes_path.exists():
            try:
                lane_config = json.loads(lanes_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                lane_config = {}
        fallbacks = lane_config.get("fallbacks", {}) or {}
        report = []
        for capability, worker_ids in self._capability_index().items():
            active = []
            for worker_id in worker_ids:
                view = next((v for v in self.list_workers(db) if v.worker_id == worker_id), None)
                if view and view.status in {"available", "online", "ready"}:
                    active.append(worker_id)
            fallback_count = len(fallbacks.get(capability, []) or [])
            resilient = len(active) >= 2 or fallback_count > 0
            report.append({
                "capability": capability,
                "workers": worker_ids,
                "active_workers": active,
                "worker_count": len(active),
                "configured_fallbacks": fallback_count,
                "resilient": resilient,
                "single_point_of_failure": not resilient,
            })
        report.sort(key=lambda item: (item["resilient"], item["capability"]))
        return {
            "capabilities": report,
            "single_point_count": sum(1 for item in report if item["single_point_of_failure"]),
            "covered_count": sum(1 for item in report if item["resilient"]),
            "total_capabilities": len(report),
        }

    def _capability_index(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for view in self.list_workers():
            for capability in view.capabilities:
                index.setdefault(capability, []).append(view.worker_id)
        return index

    def status(self, db=None) -> dict[str, Any]:
        workers = []
        for view in self.list_workers(db):
            health = db.agent_health(view.worker_id) if db is not None else {}
            circuit = (
                db.worker_circuit_state(view.worker_id)
                if db is not None
                else {"open": False, "consecutive_failures": 0, "last_event": None, "seen": False}
            )
            workers.append({
                "id": view.worker_id,
                "name": view.name,
                "department": view.contract.department,
                "status": view.status,
                "capabilities": list(view.capabilities),
                "permissions": list(view.contract.permissions),
                "health": {
                    **health,
                    "circuit": circuit,
                },
            })
        capabilities = {}
        for worker in workers:
            for capability in worker["capabilities"]:
                capabilities.setdefault(capability, []).append(worker["id"])
        return {
            "workers": workers,
            "capabilities": capabilities,
            "worker_count": len(workers),
            "capability_count": len(capabilities),
        }
