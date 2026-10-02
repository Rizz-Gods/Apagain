import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ResolveResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class ResolveBridge:
    id = "resolve-bridge"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.config_path = self.root / "config" / "production.json"
        self.state_path = self.root / "data" / "resolve_state.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "resolve-bridge"

    def _read(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _save(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _config(self) -> dict[str, Any]:
        return self._read(self.config_path, {})

    def _find_executable(self) -> Path | None:
        config = self._config()
        candidates = [Path(x) for x in config.get("executable_candidates", [])]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        found = shutil.which("Resolve")
        if found:
            return Path(found)
        return None

    def _version(self, executable: Path) -> str | None:
        try:
            proc = subprocess.run(
                [str(executable), "--version"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            text = (proc.stdout or proc.stderr or "").strip()
            match = re.search(r"(?i)resolve\s+(\d+(?:\.\d+)+)", text)
            return match.group(1) if match else None
        except Exception:
            return None

    def _script_candidates(self) -> list[Path]:
        roots = [
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            / "Blackmagic Design"
            / "DaVinci Resolve",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Blackmagic Design"
            / "DaVinci Resolve",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        ]
        results = []
        for root in roots:
            if root.exists():
                results.extend(root.rglob("DaVinciResolveScript.py"))
        return results

    def _status(self) -> dict[str, Any]:
        executable = self._find_executable()
        version = self._version(executable) if executable else None
        scripts = [str(x) for x in self._script_candidates()]
        return {
            "installed": bool(executable),
            "executable": str(executable) if executable else None,
            "version": version,
            "script_api_found": bool(scripts),
            "script_api_paths": scripts[:10],
            "external_scripting_ready": bool(executable and scripts),
        }

    def execute(self, action: str, payload: dict) -> ResolveResult:
        source = payload.get("input", {})
        if action == "status":
            status = self._status()
            self._save(self.state_path, status)
            return ResolveResult(True, status)

        if action == "launch":
            executable = self._find_executable()
            if not executable:
                return ResolveResult(True, {
                    "status": "not_installed",
                    "next": "Install DaVinci Resolve Studio 21.1 or newer.",
                })
            try:
                proc = subprocess.Popen([str(executable)], cwd=str(executable.parent))
                result = {
                    "status": "launched",
                    "pid": proc.pid,
                    "executable": str(executable),
                }
                self._save(self.state_path, {**self._status(), **result})
                return ResolveResult(True, result)
            except OSError as exc:
                return ResolveResult(False, {}, f"Unable to launch Resolve: {exc}")

        if action == "prepare_project":
            status = self._status()
            if not status["external_scripting_ready"]:
                return ResolveResult(True, {
                    "status": "waiting_for_resolve",
                    "requirements": [
                        "DaVinci Resolve Studio installed",
                        "Resolve external scripting available",
                    ],
                })
            manifest = source.get("manifest") or {}
            project = {
                "name": str(manifest.get("project_name") or "OTH Social Production"),
                "campaign_id": manifest.get("campaign_id"),
                "platform": manifest.get("platform"),
                "format": manifest.get("format"),
                "timeline": manifest.get("timeline", {}),
                "assets": manifest.get("assets", []),
                "captions": manifest.get("captions", {}),
                "audio": manifest.get("audio", {}),
                "render": manifest.get("render", {}),
            }
            return ResolveResult(True, {
                "status": "project_manifest_ready",
                "project": project,
                "next": ["launch", "connect", "build_timeline", "render", "qa"],
            })

        return ResolveResult(False, {}, f"Unsupported resolve-bridge action: {action}")
