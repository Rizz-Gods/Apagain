import shutil
import subprocess
from typing import Any
from dataclasses import dataclass

@dataclass
class ExternalResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class ExternalAgentWorker:
    def __init__(self, agent):
        self.agent = agent
        self.id = agent.id
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
        memory_context = str(payload.get("memory_context", "")).strip()
        if skill_context or memory_context:
            prompt = (
                "You are an OTH worker. Use the supplied acquired skills and "
                "past execution memory as context. Do not execute bundled scripts "
                "unless the task explicitly requires it and OTH policy permits it.\n\n"
                f"ACQUIRED SKILLS:\n{skill_context}\n\n"
                f"PAST EXECUTION MEMORY:\n{memory_context}\n\n"
                f"TASK:\n{prompt}"
            )
        cmd = [self.command, self.oneshot_flag, prompt]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=180, check=False)
        except subprocess.TimeoutExpired as exc:
            return ExternalResult(False, {}, str(exc), retryable=True)
        except Exception as exc:
            return ExternalResult(False, {}, str(exc), retryable=False)
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        if proc.returncode != 0:
            joined = f"{out}\n{err}".lower()
            permanent = any(token in joined for token in (
                "billing", "credits exhausted", "http 402", "401",
                "403", "authentication", "invalid api key"
            ))
            retryable = (not permanent) and (
                "429" in joined or "timeout" in joined or
                "temporarily" in joined or "connection" in joined or
                "502" in joined or "503" in joined or "504" in joined
            )
            return ExternalResult(
                False,
                {"stdout": out, "stderr": err},
                f"exit_code={proc.returncode}",
                retryable=retryable,
            )
        return ExternalResult(True, {"response": out, "stderr": err})
