import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FallbackResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class _BaseFallback:
    fallback = True

    def _unsupported(self, capability: str, action: str) -> FallbackResult:
        return FallbackResult(False, {"fallback": True, "capability": capability}, f"Unsupported {capability} action: {action}")


class AutomationBuilderFallback(_BaseFallback):
    id = "automation-builder-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "automation-build"

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:64] or "automation"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "build":
            return self._unsupported("automation-build", action)
        blueprints = payload.get("input", {}).get("blueprints", [])
        if not isinstance(blueprints, list):
            return FallbackResult(False, {"fallback": True}, "input.blueprints must be a list")
        projects, rejected = [], []
        for item in blueprints[:5]:
            quality = float(item.get("quality", 0) or 0)
            score = item.get("score", {}) or {}
            viability = float(score.get("score", 0) or 0)
            if quality < 0.65 or viability < 65:
                rejected.append({
                    "title": item.get("title", ""),
                    "quality": quality,
                    "viability": viability,
                    "reason": "candidate_quality_gate",
                })
                continue
            blueprint = dict(item.get("blueprint", item))
            title = blueprint.get("title", "Automation")
            project = self.root / "businesses" / self._slug(title)
            project.mkdir(parents=True, exist_ok=True)
            (project / "manifest.json").write_text(json.dumps({
                "version": 1,
                "title": title,
                "problem": blueprint.get("problem", ""),
                "automation": blueprint.get("automation", ""),
                "workflow": blueprint.get("workflow", []),
                "stack": blueprint.get("stack", []),
                "complexity": blueprint.get("estimated_complexity", "unknown"),
                "generator": self.id,
            }, indent=2), encoding="utf-8")
            (project / "workflow.json").write_text(json.dumps({
                "name": title,
                "trigger": "event",
                "steps": blueprint.get("workflow", []),
                "human_approval": ["external", "financial", "irreversible"],
            }, indent=2), encoding="utf-8")
            (project / "README.md").write_text(
                f"# {title}\n\n{blueprint.get('problem', '')}\n\n"
                + "\n".join(f"{i+1}. {s}" for i, s in enumerate(blueprint.get("workflow", [])))
                + "\n",
                encoding="utf-8",
            )
            projects.append({
                "project_path": str(project),
                "title": title,
                "manifest": blueprint,
                "opportunity": {
                    "source": item.get("source"),
                    "url": item.get("url"),
                    "query": item.get("query"),
                },
            })
        return FallbackResult(True, {
            "fallback": True,
            "projects": projects,
            "count": len(projects),
            "rejected": rejected,
            "next": [{"capability": "workflow-compile", "action": "compile", "priority": 52}],
        })


class QAFallback(_BaseFallback):
    id = "qa-validator-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "qa-validation"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "validate":
            return self._unsupported("qa-validation", action)
        projects = payload.get("input", {}).get("projects", [])
        if not isinstance(projects, list):
            return FallbackResult(False, {"fallback": True}, "input.projects must be a list")
        results = []
        for item in projects[:20]:
            raw = Path(str(item.get("project_path", "")))
            path = raw if raw.is_absolute() else self.root / raw
            checks = []
            for name in ("manifest.json", "workflow.json", "README.md"):
                checks.append({
                    "name": f"artifact:{name}",
                    "passed": (path / name).is_file(),
                })
            workflow_path = path / "workflow.json"
            if workflow_path.is_file():
                try:
                    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
                    checks.append({"name": "workflow_json", "passed": isinstance(workflow, dict)})
                    steps = workflow.get("steps", [])
                    checks.append({"name": "workflow_steps", "passed": isinstance(steps, list) and len(steps) > 0})
                except Exception:
                    checks.append({"name": "workflow_json", "passed": False})
            passed = all(x["passed"] for x in checks)
            results.append({
                "project_path": str(path),
                "status": "passed" if passed else "warnings",
                "passed": passed,
                "warnings": [x["name"] for x in checks if not x["passed"]],
                "checks": checks,
                "fallback": True,
                "verification_mode": "structural",
                "opportunity": item.get("opportunity", {}),
            })
        output = {"fallback": True, "results": results, "count": len(results)}
        if any(r["status"] == "warnings" for r in results):
            output["next"] = [{"capability": "dependency-provision", "action": "plan", "priority": 48}]
        return FallbackResult(True, output)


class PromotionFallback(_BaseFallback):
    id = "promotion-gate-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "promotion-gate"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "promote":
            return self._unsupported("promotion-gate", action)
        rows = payload.get("input", {}).get("results", [])
        if not isinstance(rows, list):
            return FallbackResult(False, {"fallback": True}, "input.results must be a list")
        decisions = []
        for row in rows[:20]:
            status = str(row.get("status", "failed"))
            decision = "ready" if status == "passed" else "held" if status == "warnings" else "rejected"
            decisions.append({
                "project_path": str(row.get("project_path", "")),
                "opportunity": row.get("opportunity", {}) or {},
                "status": decision,
                "reason": {
                    "ready": "Structural QA passed; eligible for promotion review",
                    "held": "Warnings present; promotion remains held",
                    "rejected": "QA failed; promotion blocked",
                }[decision],
                "fallback": True,
            })
        return FallbackResult(True, {"fallback": True, "decisions": decisions, "count": len(decisions)})


class DependencyProvisionFallback(_BaseFallback):
    id = "dependency-provisioner-fallback"
    ALLOWLIST = {
        "node-red": ("npm", "node-red"),
        "n8n": ("npm", "n8n"),
        "agent-browser": ("npm", "agent-browser"),
    }

    def supports(self, capability: str) -> bool:
        return capability == "dependency-provision"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "plan":
            return self._unsupported("dependency-provision", action)
        source = payload.get("input", {})
        warnings = list(source.get("warnings", []) or [])
        for row in source.get("results", []) or []:
            warnings.extend(row.get("warnings", []) if isinstance(row, dict) else [])
        plans = []
        seen = set()
        for warning in warnings:
            text = str(warning).lower()
            for name, (manager, binary) in self.ALLOWLIST.items():
                if name in text and name not in seen:
                    seen.add(name)
                    plans.append({
                        "dependency": name,
                        "installed": bool(shutil.which(f"{binary}.cmd") or shutil.which(binary)),
                        "manager": manager,
                        "action": "install",
                        "mode": "plan-only",
                    })
        return FallbackResult(True, {"fallback": True, "plans": plans, "count": len(plans)})


class WorkflowCompilerFallback(_BaseFallback):
    id = "workflow-compiler-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "workflow-compile"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "compile":
            return self._unsupported("workflow-compile", action)
        projects = payload.get("input", {}).get("projects", [])
        if not isinstance(projects, list):
            return FallbackResult(False, {"fallback": True}, "input.projects must be a list")
        compiled = []
        for item in projects[:10]:
            raw = Path(str(item.get("project_path", "")))
            path = raw if raw.is_absolute() else self.root / raw
            workflow = json.loads((path / "workflow.json").read_text(encoding="utf-8"))
            steps = workflow.get("steps", [])
            draft = {
                "name": workflow.get("name", "OTH Automation"),
                "trigger": workflow.get("trigger", "event"),
                "steps": steps,
                "active": False,
                "generated_by": self.id,
                "provider_neutral": True,
            }
            target = path / "oth.workflow.fallback.json"
            target.write_text(json.dumps(draft, indent=2), encoding="utf-8")
            compiled.append({
                "project_path": str(path),
                "workflow_path": str(target),
                "workflow_name": draft["name"],
                "nodes": len(steps) + 1,
                "active": False,
                "provider_neutral": True,
                "opportunity": item.get("opportunity", {}),
            })
        return FallbackResult(True, {
            "fallback": True,
            "compiled": compiled,
            "count": len(compiled),
            "next": [{"capability": "qa-validation", "action": "validate", "priority": 50}],
        })


class MediaQAFallback(_BaseFallback):
    id = "media-qa-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "media-qa"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "check":
            return self._unsupported("media-qa", action)
        source = payload.get("input", {})
        media_ref = str(source.get("media_ref", "")).strip()
        if not media_ref:
            return FallbackResult(False, {"fallback": True}, "media_ref is required")
        raw = Path(media_ref).expanduser()
        path = raw if raw.is_absolute() else self.root / raw
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(self.root.resolve()):
            return FallbackResult(False, {"fallback": True}, "media_ref must resolve inside the OTH workspace")
        suffix = path.suffix.lower()
        supported = suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".wav", ".mp3", ".m4a"}
        issues = [] if supported else ["unsupported_media_extension"]
        if path.stat().st_size == 0:
            issues.append("empty_media")
        return FallbackResult(True, {
            "fallback": True,
            "media_ref": str(path.relative_to(self.root)),
            "size_bytes": path.stat().st_size,
            "format": suffix.lstrip("."),
            "issues": issues,
            "passed": not issues,
            "verification_mode": "filesystem-structural",
        })


class MediaTranscriptionFallback(_BaseFallback):
    id = "media-transcription-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.out_dir = self.root / "data" / "media" / "captions"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "media-transcription"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "transcribe":
            return self._unsupported("media-transcription", action)
        source = payload.get("input", {})
        media_ref = str(source.get("media_ref", "")).strip()
        text = str(source.get("transcript_text", "")).strip()
        if not media_ref:
            return FallbackResult(False, {"fallback": True}, "media_ref is required")
        if not text:
            sidecar = Path(media_ref).expanduser()
            if not sidecar.is_absolute():
                sidecar = self.root / sidecar
            sidecar = sidecar.with_suffix(".txt")
            if sidecar.is_file():
                text = sidecar.read_text(encoding="utf-8").strip()
        if not text:
            return FallbackResult(False, {"fallback": True, "mode": "sidecar-import"}, "No transcript backend or sidecar text available", retryable=True)
        words = text.split()
        duration = float(source.get("duration_seconds", 0) or 0)
        end = max(duration, 1.0)
        srt_path = self.out_dir / f"{Path(media_ref).stem}.fallback.srt"
        srt_path.write_text(f"1\n00:00:00,000 --> 00:00:{int(end):02},000\n{text}\n", encoding="utf-8")
        return FallbackResult(True, {
            "fallback": True,
            "mode": "sidecar-import",
            "media_ref": str(Path(media_ref)),
            "language": source.get("language", "unknown"),
            "duration": end,
            "segments": [{"start": 0.0, "end": end, "text": text, "words": []}],
            "srt_path": str(srt_path.relative_to(self.root)),
        })
