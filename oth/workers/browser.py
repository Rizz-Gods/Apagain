import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
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
        configured_browser = agent.metadata.get("browser_executable")
        self.browser_executable = (
            str(Path(configured_browser).expanduser())
            if configured_browser
            else ""
        )
        profile = agent.metadata.get("browser_profile")
        self.browser_profile = str(profile) if profile else ""

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
            command_line = [self.command]
            if self.browser_executable and Path(self.browser_executable).exists():
                command_line.extend(["--executable-path", self.browser_executable])
            if self.browser_profile:
                profile_path = Path(self.browser_profile)
                profile_path.parent.mkdir(parents=True, exist_ok=True)
                command_line.extend(["--profile", str(profile_path)])
            command_line.extend(["--session", self.session, command, *args])
            proc = subprocess.run(
                command_line,
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
        return BrowserResult(True, {
            "stdout": out,
            "stderr": err,
            "browser": self.browser_executable if self.browser_executable and Path(self.browser_executable).exists() else "agent-browser-managed-chromium",
            "profile": self.browser_profile or None,
            "session": self.session,
        })
