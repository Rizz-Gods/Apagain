import shutil
import subprocess
from typing import Any
from dataclasses import dataclass

@dataclass
class ExternalResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None

class ExternalAgentWorker:
    def __init__(self, agent):
        self.agent = agent
        self.command = agent.metadata.get("command")
        self.oneshot_flag = agent.metadata.get("oneshot_flag", "-z")

    def supports(self, capability: str) -> bool:
        return capability in self.agent.capabilities and bool(shutil.which(self.command))

    def execute(self, action: str, payload: dict[str, Any]) -> ExternalResult:
        if action != "prompt":
            return ExternalResult(False, {}, f"Unsupported action: {action}")
        prompt = str(payload.get("prompt", ""))
        if not prompt:
            return ExternalResult(False, {}, "Missing prompt")
        skill_context = str(payload.get("skill_context", "")).strip()
        if skill_context:
            prompt = (
                "You are an OTH worker. Use the following acquired skills as "
                "procedural context. Do not execute bundled scripts unless the "
                "task explicitly requires it and the OTH policy permits it.\n\n"
                f"{skill_context}\n\nTASK:\n{prompt}"
            )
        cmd = [self.command, self.oneshot_flag, prompt]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=180, check=False)
        except Exception as exc:
            return ExternalResult(False, {}, str(exc))
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        if proc.returncode != 0:
            return ExternalResult(False, {"stdout": out, "stderr": err},
                                  f"exit_code={proc.returncode}")
        return ExternalResult(True, {"response": out, "stderr": err})
