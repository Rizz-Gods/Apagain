import shutil
from dataclasses import dataclass
from typing import Any

@dataclass
class ProvisionResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class DependencyProvisioner:
    id = "dependency-provisioner"

    ALLOWLIST = {
        "n8n": {
            "manager": "npm",
            "command": ["npm.cmd", "install", "-g", "n8n"],
            "binary": "n8n.cmd",
        },
        "agent-browser": {
            "manager": "npm",
            "command": ["npm.cmd", "install", "-g", "agent-browser"],
            "binary": "agent-browser.cmd",
        },
    }

    def supports(self, capability: str) -> bool:
        return capability == "dependency-provision"

    def execute(self, action: str, payload: dict) -> ProvisionResult:
        if action != "plan":
            return ProvisionResult(False, {}, f"Unsupported dependency-provision action: {action}")
        warnings = payload.get("input", {}).get("warnings", [])
        if not isinstance(warnings, list):
            return ProvisionResult(False, {}, "input.warnings must be a list")

        plans = []
        for warning in warnings:
            text = str(warning)
            for name, spec in self.ALLOWLIST.items():
                if name in text.lower():
                    installed = shutil.which(spec["binary"]) is not None
                    plans.append({
                        "dependency": name,
                        "installed": installed,
                        "manager": spec["manager"],
                        "command": spec["command"],
                        "action": "no-op" if installed else "install",
                    })
        return ProvisionResult(True, {
            "plans": plans,
            "count": len(plans),
        })
