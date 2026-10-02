import json
from pathlib import Path
from dataclasses import dataclass

@dataclass
class PolicyDecision:
    allowed: bool
    reason: str

class PolicyGate:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.exists():
            self.config = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.config = {
                "external_actions_require_approval": True,
                "financial_actions_require_approval": True,
            }

    def check(self, payload: dict) -> PolicyDecision:
        risk = str(payload.get("risk", "safe")).lower()
        if risk == "safe":
            return PolicyDecision(True, "safe")
        if risk == "local_write":
            return PolicyDecision(True, "local_write")
        if risk == "external" and self.config.get("external_actions_require_approval", True):
            return PolicyDecision(False, "external_action_requires_approval")
        if risk == "financial" and self.config.get("financial_actions_require_approval", True):
            return PolicyDecision(False, "financial_action_requires_approval")
        return PolicyDecision(True, f"allowed:{risk}")
