import importlib
import json
import os
import re
import shutil
import subprocess
import time
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

    def _script_environment(self) -> dict[str, str]:
        program_data = Path(os.environ.get("PROGRAMDATA", r"C:\\ProgramData"))
        program_files = Path(os.environ.get("PROGRAMFILES", r"C:\\Program Files"))
        api_root = program_data / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting"
        lib = program_files / "Blackmagic Design" / "DaVinci Resolve" / "fusionscript.dll"
        modules = api_root / "Modules"
        return {"api": str(api_root), "modules": str(modules), "lib": str(lib)}

    def _connect(self) -> tuple[Any | None, dict[str, str]]:
        env = self._script_environment()
        if Path(env["modules"]).is_dir():
            os.environ["RESOLVE_SCRIPT_API"] = env["api"]
            os.environ["RESOLVE_SCRIPT_LIB"] = env["lib"]
            path_entries = [x for x in os.environ.get("PYTHONPATH", "").split(os.pathsep) if x]
            if env["modules"] not in path_entries:
                os.environ["PYTHONPATH"] = os.pathsep.join(path_entries + [env["modules"]])
        try:
            module = importlib.import_module("DaVinciResolveScript")
            return module.scriptapp("Resolve"), env
        except Exception:
            return None, env

    def _status(self) -> dict[str, Any]:
        executable = self._find_executable()
        version = self._version(executable) if executable else None
        scripts = [str(x) for x in self._script_candidates()]
        env = self._script_environment()
        resolve, _ = self._connect() if executable and scripts else (None, env)
        return {
            "installed": bool(executable),
            "executable": str(executable) if executable else None,
            "version": version,
            "script_api_found": bool(scripts),
            "script_api_paths": scripts[:10],
            "script_environment": env,
            "connected": resolve is not None,
            "project_manager_available": bool(resolve and resolve.GetProjectManager()),
            "external_scripting_ready": bool(executable and scripts),
        }

    def _build_project(self, manifest: dict[str, Any]) -> dict[str, Any]:
        resolve, env = self._connect()
        if resolve is None:
            return {"status": "not_connected", "script_environment": env}
        manager = resolve.GetProjectManager()
        if manager is None:
            return {"status": "project_manager_unavailable"}

        name = str(manifest.get("project_name") or manifest.get("campaign_id") or "OTH Social Production")[:100]
        project = None
        try:
            existing = manager.GetProjectList() or []
            if name in existing:
                project = manager.LoadProject(name)
            else:
                project = manager.CreateProject(name)
        except Exception as exc:
            return {"status": "project_create_failed", "error": str(exc)}
        if project is None:
            return {"status": "project_unavailable", "project_name": name}

        render = manifest.get("render") or {}
        resolution = str(render.get("resolution") or "1080x1920")
        try:
            width, height = resolution.lower().split("x", 1)
            project.SetSetting("timelineResolutionWidth", width)
            project.SetSetting("timelineResolutionHeight", height)
            project.SetSetting("timelineFrameRate", str(render.get("frame_rate") or 30))
            project.SetSetting("timelinePlaybackFrameRate", str(render.get("frame_rate") or 30))
        except Exception:
            pass

        timeline_name = str(manifest.get("timeline_name") or f"{name} Timeline")[:100]
        media_pool = project.GetMediaPool()
        timeline = None
        if media_pool:
            try:
                timeline = media_pool.CreateEmptyTimeline(timeline_name)
                if timeline:
                    project.SetCurrentTimeline(timeline)
            except Exception:
                timeline = None

        if timeline:
            for segment in manifest.get("timeline", []) or []:
                try:
                    start = int(round(float(segment.get("start", 0)) * float(render.get("frame_rate") or 30)))
                    duration = max(1, int(round((float(segment.get("end", 1)) - float(segment.get("start", 0))) * float(render.get("frame_rate") or 30))))
                    timeline.AddMarker(start, "Blue", str(segment.get("id", "segment")), str(segment.get("purpose", "")), duration, "oth")
                except Exception:
                    continue
        return {
            "status": "project_ready",
            "project_name": project.GetName(),
            "timeline_name": timeline.GetName() if timeline else None,
            "render": render,
        }

    def execute(self, action: str, payload: dict) -> ResolveResult:
        source = payload.get("input", {})
        if action == "status":
            status = self._status()
            self._save(self.state_path, status)
            return ResolveResult(True, status)

        if action == "connect":
            resolve, env = self._connect()
            if resolve is None:
                return ResolveResult(True, {
                    "status": "not_connected",
                    "script_environment": env,
                    "next": "Launch Resolve and enable External Scripting Using: Local.",
                })
            return ResolveResult(True, {
                "status": "connected",
                "script_environment": env,
                "project_manager_available": bool(resolve.GetProjectManager()),
            })

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
            manifests = source.get("manifests") or []
            manifest = source.get("manifest") or (manifests[0] if isinstance(manifests, list) and manifests else {})
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
                "next": ["launch", "connect", "build_project", "render", "qa"],
            })

        if action == "build_project":
            manifest = source.get("manifest") or {}
            result = self._build_project(manifest)
            if result.get("status") in {"not_connected", "project_manager_unavailable"}:
                return ResolveResult(True, result)
            self._save(self.state_path, {**self._status(), **result})
            return ResolveResult(True, result)

        return ResolveResult(False, {}, f"Unsupported resolve-bridge action: {action}")
