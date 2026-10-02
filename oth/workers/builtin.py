from dataclasses import dataclass
from typing import Any

@dataclass
class WorkerResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None

class BuiltinWorker:
    id = "builtin"

    def supports(self, capability: str) -> bool:
        return capability == "demo"

    def execute(self, action: str, payload: dict[str, Any]) -> WorkerResult:
        if action == "echo":
            message = str(payload.get("message", ""))
            return WorkerResult(True, {"message": message})
        return WorkerResult(False, {}, f"Unsupported builtin action: {action}")
