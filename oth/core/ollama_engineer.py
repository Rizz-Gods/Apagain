from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from .model_router import ModelRoute, ModelRouter
from .engineering_evidence import implementation_expected, workspace_changed, workspace_fingerprint


class NativeOllamaEngineer:
    id = "ollama-engineer"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.router = ModelRouter(self.root)
        self.max_steps = 24

    def supports(self, capability: str) -> bool:
        return capability == "engineering"

    def _base_url(self) -> str:
        try:
            proc = subprocess.run(
                ["wsl.exe", "-d", "Arch", "--", "bash", "-lc",
                 "ip -4 -o addr show eth0 | sed -n 's/.*inet \\([0-9.]*\\)\\/.*/\\1/p'"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            for line in proc.stdout.splitlines():
                ip = line.strip()
                if re.fullmatch(r"\d+(?:\.\d+){3}", ip):
                    return f"http://{ip}:11434/v1"
        except Exception:
            pass
        return os.getenv("OTH_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

    def _path(self, raw: str) -> Path:
        value = str(raw or ".").strip()
        if value in {"", ".", "/", "/repository", "repository"}:
            return self.root
        candidate = Path(value)
        if candidate.is_absolute():
            raise ValueError("absolute paths are not permitted")
        resolved = (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise ValueError("path escapes repository")
        return resolved

    def _list_files(self, path: str = ".") -> dict[str, Any]:
        root = self._path(path)
        items = []
        iterator = root.rglob("*") if root.is_dir() else [root]
        for item in iterator:
            if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in item.parts):
                continue
            items.append(str(item.relative_to(self.root)))
            if len(items) >= 160:
                break
        return {"files": items}

    def _read_file(self, path: str, start_line: int = 1, end_line: int = 220) -> dict[str, Any]:
        target = self._path(path)
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, int(start_line))
        end = min(len(lines), max(start, int(end_line)))
        return {
            "path": str(target.relative_to(self.root)),
            "content": "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))[:16000],
            "total_lines": len(lines),
        }

    def _search(self, query: str, path: str = ".") -> dict[str, Any]:
        query = str(query or "").lower()
        root = self._path(path)
        matches = []
        iterator = root.rglob("*") if root.is_dir() else [root]
        for item in iterator:
            if not item.is_file() or any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in item.parts):
                continue
            try:
                lines = item.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if query in line.lower():
                    matches.append({"path": str(item.relative_to(self.root)), "line": i, "text": line[:500]})
                    if len(matches) >= 60:
                        return {"matches": matches}
        return {"matches": matches}

    def _write(self, path: str, content: str) -> dict[str, Any]:
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = str(content)
        if len(text) > 500000:
            raise ValueError("file content too large")
        target.write_text(text, encoding="utf-8")
        return {"path": str(target.relative_to(self.root)), "written": len(text)}

    def _replace(self, path: str, old_text: str, new_text: str) -> dict[str, Any]:
        target = self._path(path)
        text = target.read_text(encoding="utf-8", errors="replace")
        if old_text not in text:
            raise ValueError("old_text not found")
        target.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return {"path": str(target.relative_to(self.root)), "replaced": True}

    def _run(self, command: str) -> dict[str, Any]:
        command = str(command or "").strip()
        if not command or len(command) > 1000:
            raise ValueError("invalid command")
        if any(token in command for token in ["&", "|", ">", "<"]):
            raise ValueError("shell chaining is not permitted")
        blocked = ["del ", "erase ", "rmdir ", "format ", "shutdown ", "taskkill ", "netsh ", "curl ", "wget ", "powershell "]
        if any(command.lower().startswith(token) for token in blocked):
            raise ValueError("command blocked by OTH safety policy")
        allowed = ("python ", "python.exe ", "pytest ", "git ", "node ", "npm ", "ruff ", ".venv\\Scripts\\python.exe ")
        if not command.lower().startswith(allowed):
            raise ValueError("command outside safe engineering allowlist")
        proc = subprocess.run(command, cwd=self.root, shell=True, capture_output=True, text=True, timeout=180, check=False)
        return {"returncode": proc.returncode, "stdout": proc.stdout[-12000:], "stderr": proc.stderr[-8000:]}

    def _git(self, args: list[str]) -> dict[str, Any]:
        proc = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, timeout=60, check=False)
        return {"returncode": proc.returncode, "stdout": proc.stdout[-12000:], "stderr": proc.stderr[-6000:]}

    def _tools(self) -> list[dict[str, Any]]:
        def t(name: str, description: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
            return {"type": "function", "function": {
                "name": name, "description": description,
                "parameters": {"type": "object", "properties": props, "required": required}
            }}
        return [
            t("list_files", "List repository files.", {"path": {"type": "string"}}, ["path"]),
            t("read_file", "Read a source file.", {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, ["path"]),
            t("search_text", "Search repository text.", {"query": {"type": "string"}, "path": {"type": "string"}}, ["query"]),
            t("write_file", "Create or replace a file.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
            t("replace_text", "Replace one exact text block.", {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, ["path", "old_text", "new_text"]),
            t("run_command", "Run safe local engineering commands.", {"command": {"type": "string"}}, ["command"]),
            t("git_status", "Show Git working tree status.", {}, []),
            t("git_diff", "Show current Git diff.", {}, []),
            t("finish", "Finish with a concise mission summary.", {"summary": {"type": "string"}}, ["summary"]),
        ]

    def _tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "list_files":
            return self._list_files(args.get("path", "."))
        if name == "read_file":
            return self._read_file(args["path"], args.get("start_line", 1), args.get("end_line", 220))
        if name == "search_text":
            return self._search(args["query"], args.get("path", "."))
        if name == "write_file":
            return self._write(args["path"], args["content"])
        if name == "replace_text":
            return self._replace(args["path"], args["old_text"], args["new_text"])
        if name == "run_command":
            return self._run(args["command"])
        if name == "git_status":
            return self._git(["status", "--short"])
        if name == "git_diff":
            return self._git(["diff", "--", "."])
        raise ValueError(f"unknown tool: {name}")

    @staticmethod
    def _parse_text_tool(content: str):
        raw = (content or "").strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                obj = json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                return None
        if isinstance(obj, dict) and obj.get("name"):
            args = obj.get("arguments", {}) or {}
            return str(obj["name"]), args if isinstance(args, dict) else {}
        return None

    def _chat(self, base: str, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {"model": model, "messages": messages, "tools": self._tools(), "temperature": 0.1}
        request = urllib.request.Request(
            base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))

    def execute(self, action: str, payload: dict[str, Any]):
        from oth.workers.builtin import WorkerResult

        if action not in {"execute", "build", "repair"}:
            return WorkerResult(False, {}, f"Unsupported engineering action: {action}")
        task = str(payload.get("prompt") or payload.get("message") or payload.get("input") or "").strip()
        if not task:
            return WorkerResult(False, {}, "Missing engineering mission")

        route = self.router.route(task)
        if not route.model:
            return WorkerResult(False, {"complexity": route.complexity}, "model_route_unavailable")
        model = route.model.split("/", 1)[1] if "/" in route.model else route.model
        base = self._base_url()

        try:
            req = urllib.request.Request(base.replace("/v1", "") + "/api/tags")
            with urllib.request.urlopen(req, timeout=3) as response:
                installed = {str(item.get("name", "")).strip() for item in json.loads(response.read().decode("utf-8")).get("models", []) if item.get("name")}
        except Exception:
            installed = set()
        if model not in installed:
            fallback = self.router._profile("local")
            model = fallback.split("/", 1)[1] if "/" in fallback else fallback
            route = ModelRoute("local-fallback", fallback, route.complexity, f"requested {route.model} unavailable locally")

        before = self._git(["status", "--short"])
        workspace_before = workspace_fingerprint(self.root)
        requires_change = implementation_expected(action, task, payload)
        messages = [
            {"role": "system", "content":
             "You are OTH Native Engineering. Modify the repository using tools and verify your work. "
             "Never claim success without tool evidence. Do not commit or push. "
             "For each tool action, emit one JSON object with name and arguments. "
             "Run OTH CLI commands as `python -m oth.cli ...`, never as `oth.cli ...`. "
             "When done, emit a finish JSON object with a summary. "
             f"Repository: {self.root}. Model tier: {route.tier}."},
            {"role": "user", "content": task},
        ]

        trace = []
        summary = ""
        finished = False
        for _ in range(self.max_steps):
            response = self._chat(base, model, messages)
            message = (response.get("choices") or [{}])[0].get("message") or {}
            content = str(message.get("content") or "").strip()
            parsed = self._parse_text_tool(content)
            if not parsed:
                calls = message.get("tool_calls") or []
                if calls:
                    fn = calls[0].get("function") or {}
                    name = str(fn.get("name") or "")
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    parsed = (name, args)
            if not parsed:
                summary = content
                break
            name, args = parsed
            if name == "finish":
                summary = str(args.get("summary") or "Mission completed.")
                finished = True
                break
            try:
                result = self._tool(name, args)
                trace.append({"tool": name, "success": True})
            except Exception as exc:
                result = {"error": str(exc)}
                trace.append({"tool": name, "success": False, "error": str(exc)})
            text = json.dumps(result, ensure_ascii=False)
            if len(text) > 14000:
                text = text[-14000:]
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"TOOL RESULT ({name}):\n{text}\nContinue."})

        verification = self._run("python -m pytest -q") if (self.root / "pytest.ini").exists() else {"returncode": 0, "stdout": "no pytest.ini", "stderr": ""}
        after = self._git(["status", "--short"])
        workspace_after = workspace_fingerprint(self.root)
        changed = workspace_changed(workspace_before, workspace_after)
        failed_tools = [item for item in trace if not item.get("success")]
        success = (
            verification.get("returncode") == 0
            and finished
            and not failed_tools
            and (changed or not requires_change)
        )
        return WorkerResult(
            success,
            {
                "provider": "ollama-native",
                "model": route.model,
                "tier": route.tier,
                "complexity": route.complexity,
                "steps": len(trace),
                "summary": summary[-8000:],
                "tool_trace": trace[-40:],
                "changed_before": before,
                "changed_after": after,
                "workspace_before": workspace_before,
                "workspace_after": workspace_after,
                "implementation_changed": changed,
                "implementation_expected": requires_change,
                "verification": verification,
            },
            None if success else "engineering_verification_failed",
            retryable=not success,
        )
