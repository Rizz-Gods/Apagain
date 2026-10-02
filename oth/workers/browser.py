import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

@dataclass
class BrowserResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class BrowserWorker:
    id = "browser"
    ALLOWED = {
        "open", "read", "click", "dblclick", "type", "fill", "press",
        "hover", "check", "uncheck", "select", "scroll", "scrollintoview",
        "wait", "snapshot", "screenshot", "back", "forward", "reload",
        "get", "is", "find", "tab", "close", "download", "upload",
    }

    def __init__(self, agent):
        self.agent = agent
        self.command = agent.metadata.get("command", "agent-browser.cmd")
        self.session = agent.metadata.get("session", "oth")

    def supports(self, capability: str) -> bool:
        return capability == "browser" and bool(shutil.which(self.command))

    def execute(self, action: str, payload: dict[str, Any]) -> BrowserResult:
        if action != "command":
            return BrowserResult(False, {}, f"Unsupported browser action: {action}")
        command = str(payload.get("command", ""))
        args = payload.get("args", [])
        if command not in self.ALLOWED:
            return BrowserResult(False, {}, f"Browser command not allowed: {command}")
        if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
            return BrowserResult(False, {}, "Browser args must be a string list")
        try:
            proc = subprocess.run(
                [self.command, "--session", self.session, command, *args],
                capture_output=True, text=True, timeout=120, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return BrowserResult(False, {}, str(exc), retryable=True)
        except Exception as exc:
            return BrowserResult(False, {}, str(exc))
        out, err = proc.stdout.strip(), proc.stderr.strip()
        if proc.returncode != 0:
            joined = f"{out}\n{err}".lower()
            retryable = any(token in joined for token in ("timeout", "temporarily", "connection", "429", "502", "503", "504"))
            return BrowserResult(False, {"stdout": out, "stderr": err},
                                 f"exit_code={proc.returncode}", retryable=retryable)
        return BrowserResult(True, {"stdout": out, "stderr": err})
