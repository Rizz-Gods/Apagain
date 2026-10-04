from __future__ import annotations

from pathlib import Path
from typing import Any


class EngineeringFallback:
    """Explicit degraded lane: inspect and report, never pretend to edit."""

    id = "engineering-audit-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "engineering"

    def execute(self, action: str, payload: dict[str, Any]):
        from oth.workers.builtin import WorkerResult

        if action not in {"execute", "build", "repair"}:
            return WorkerResult(False, {}, f"Unsupported engineering action: {action}")

        task = str(payload.get("prompt") or payload.get("message") or "").strip()
        if not task:
            return WorkerResult(False, {}, "Missing engineering mission")

        return WorkerResult(
            False,
            {
                "degraded": True,
                "provider": "audit-only",
                "mission": task,
                "root": str(self.root),
                "capability": "engineering",
                "claim": "No code was changed because the execution provider is unavailable.",
            },
            "engineering_provider_unavailable",
            retryable=False,
        )
