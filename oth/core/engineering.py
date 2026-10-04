from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from .model_router import ModelRouter, ModelRoute
from .engineering_evidence import implementation_expected, workspace_changed, workspace_fingerprint


class EngineeringWorker:
    """Execution-grade local software engineer backed by OpenCode."""

    id = "opencode-engineer"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.timeout_seconds = 1800
        self.repair_cycles = 2

    def supports(self, capability: str) -> bool:
        return capability == "engineering"

    def _opencode(self) -> str | None:
        return shutil.which("opencode") or shutil.which("opencode.cmd")

    def _run(
        self,
        command: list[str],
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )

    def _ollama_base_url(self) -> str:
        try:
            proc = subprocess.run(
                [
                    "wsl.exe", "-d", "Arch", "--", "bash", "-lc",
                    "ip -4 -o addr show eth0 | sed -n 's/.*inet \\([0-9.]*\\)\\/.*/\\1/p'",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            ip = next((line.strip() for line in proc.stdout.splitlines() if re.fullmatch(r"\d+(?:\.\d+){3}", line.strip())), "")
            if ip:
                return f"http://{ip}:11434/v1"
        except Exception:
            pass
        return os.getenv("OTH_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

    def _test_command(self) -> list[str] | None:
        python = self.root / ".venv" / "Scripts" / "python.exe"
        if (self.root / "pytest.ini").exists() and python.exists():
            return [str(python), "-m", "pytest", "-q"]
        return None

    def _prompt(self, task: str, prior_failure: str = "") -> str:
        repair = ""
        if prior_failure:
            repair = (
                "\nA previous verification cycle failed. Fix the actual failure before "
                "doing anything else. Failure output:\n" + prior_failure[-12000:]
            )
        return (
            "You are the Engineering Worker inside Over The Horizon. "
            "You have full responsibility for completing the operator's local software mission. "
            "Work directly in the current repository. Inspect the existing architecture first. "
            "Implement the requested change rather than merely explaining it. "
            "Preserve existing behavior, safety gates, persistence, resilience, and tests. "
            "Do not make external posts, purchases, financial actions, credential changes, "
            "or irreversible external actions. Do not invent success. "
            "Use existing project tools and dependencies where practical. "
            "Run relevant tests after changes. Leave the working tree with the implementation "
            "and verification evidence present. Do not create commits or push Git history; OTH "
            "handles source control separately.\n\n"
            f"OPERATOR MISSION:\n{task}\n"
            f"{repair}"
        )

    def execute(self, action: str, payload: dict[str, Any]):
        from oth.workers.builtin import WorkerResult

        if action not in {"execute", "build", "repair"}:
            return WorkerResult(False, {}, f"Unsupported engineering action: {action}")

        task = str(payload.get("prompt") or payload.get("message") or payload.get("input") or "").strip()
        if not task:
            return WorkerResult(False, {}, "Missing engineering mission")

        command = self._opencode()
        if not command:
            return WorkerResult(
                False,
                {"provider": "opencode", "available": False},
                "provider_unavailable: OpenCode CLI is not installed",
                retryable=False,
            )

        changed_before = self._run(
            ["git", "status", "--porcelain"],
            30,
        ).stdout.strip()
        workspace_before = workspace_fingerprint(self.root)
        requires_change = implementation_expected(action, task, payload)

        failures: list[str] = []
        attempts = 0
        final_agent_output = ""

        environment = os.environ.copy()
        environment["OTH_OLLAMA_BASE_URL"] = self._ollama_base_url()
        environment["OTH_MODEL_BASE_URL"] = environment["OTH_OLLAMA_BASE_URL"]
        router = ModelRouter(self.root)
        route = router.route(task)
        if route.model.startswith("ollama/"):
            model_name = route.model.split("/", 1)[1]
            try:
                req = urllib.request.Request(
                    environment["OTH_OLLAMA_BASE_URL"].replace("/v1", "") + "/api/tags"
                )
                with urllib.request.urlopen(req, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                installed = {
                    str(item.get("name", "")).strip()
                    for item in payload.get("models", [])
                    if item.get("name")
                }
            except Exception:
                installed = set()
            if model_name not in installed:
                fallback = router._profile("local")
                route = ModelRoute(
                    "local-fallback",
                    fallback,
                    route.complexity,
                    f"requested {model_name} unavailable locally",
                )
        if not route.model:
            return WorkerResult(
                False,
                {"complexity": route.complexity, "reason": route.reason},
                "model_route_unavailable",
                retryable=False,
            )
        environment["OTH_OPENCODE_MODEL"] = route.model

        for cycle in range(self.repair_cycles + 1):
            attempts += 1
            prompt = self._prompt(task, failures[-1] if failures else "")
            try:
                proc = self._run(
                    [
                        command,
                        "run",
                        "--standalone",
                        "--agent",
                        "build",
                        "--auto",
                        "--format",
                        "json",
                        "--model",
                        route.model,
                        prompt,
                    ],
                    self.timeout_seconds,
                    env=environment,
                )
            except subprocess.TimeoutExpired as exc:
                failures.append(f"opencode timeout after {self.timeout_seconds}s: {exc}")
                continue
            except Exception as exc:
                return WorkerResult(False, {}, f"opencode launch failed: {exc}", retryable=False)

            final_agent_output = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            if proc.returncode != 0:
                failures.append(
                    f"opencode exit_code={proc.returncode}\n"
                    f"stdout={final_agent_output[-6000:]}\n"
                    f"stderr={stderr[-6000:]}"
                )
                if proc.returncode in {401, 403}:
                    return WorkerResult(False, {"stdout": final_agent_output, "stderr": stderr},
                                        "provider_authentication_failed", retryable=False)
                continue

            test_cmd = self._test_command()
            if not test_cmd:
                break

            test = self._run(test_cmd, 900)
            if test.returncode == 0:
                break

            failures.append(
                "verification_failed\n"
                f"stdout={test.stdout[-8000:]}\n"
                f"stderr={test.stderr[-8000:]}"
            )

        test_cmd = self._test_command()
        verification = None
        if test_cmd:
            try:
                test = self._run(test_cmd, 900)
                verification = {
                    "passed": test.returncode == 0,
                    "returncode": test.returncode,
                    "stdout": test.stdout[-12000:],
                    "stderr": test.stderr[-12000:],
                }
            except subprocess.TimeoutExpired:
                verification = {"passed": False, "timeout": True}

        changed_after = self._run(
            ["git", "status", "--porcelain"],
            30,
        ).stdout.strip()
        workspace_after = workspace_fingerprint(self.root)
        implementation_changed = workspace_changed(workspace_before, workspace_after)

        success = (
            not failures
            and (verification is None or verification["passed"])
            and (implementation_changed or not requires_change)
        )
        if not implementation_changed and requires_change and not failures:
            failures.append("implementation_evidence_missing: repository content did not change")
            success = False
        if not success:
            return WorkerResult(
                False,
                {
                    "provider": "opencode",
                    "attempts": attempts,
                    "changed_before": changed_before,
                    "changed_after": changed_after,
                    "workspace_before": workspace_before,
                    "workspace_after": workspace_after,
                    "implementation_changed": implementation_changed,
                    "implementation_expected": requires_change,
                    "agent_output": final_agent_output[-12000:],
                    "verification": verification,
                    "failures": failures[-3:],
                },
                "engineering_verification_failed",
                retryable=True,
            )

        return WorkerResult(
            True,
            {
                "provider": "opencode",
                "attempts": attempts,
                "changed_before": changed_before,
                "changed_after": changed_after,
                "workspace_before": workspace_before,
                "workspace_after": workspace_after,
                "implementation_changed": implementation_changed,
                "implementation_expected": requires_change,
                "agent_output": final_agent_output[-12000:],
                "verification": verification,
            },
        )
