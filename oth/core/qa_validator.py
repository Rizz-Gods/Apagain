import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class QAResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class QAValidator:
    id = "qa-validator"

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]

    def supports(self, capability: str) -> bool:
        return capability == "qa-validation"

    @staticmethod
    def _check(checks, name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        return bool(passed)

    def _validate_project(self, project: dict) -> dict:
        project_path = Path(project.get("project_path", ""))
        checks, warnings, errors = [], [], []

        if not project_path.is_absolute():
            project_path = self.root / project_path

        exists = project_path.exists() and project_path.is_dir()
        self._check(checks, "project_exists", exists, str(project_path))
        if not exists:
            return {
                "status": "failed",
                "project_path": str(project_path),
                "opportunity": project.get("opportunity", {}),
                "checks": checks,
                "warnings": warnings,
                "errors": ["project directory missing"],
            }

        required = ["manifest.json", "README.md", "workflow.json"]
        for name in required:
            self._check(checks, f"required:{name}",
                        (project_path / name).exists())

        try:
            manifest = json.loads((project_path / "manifest.json").read_text(encoding="utf-8"))
            workflow = json.loads((project_path / "workflow.json").read_text(encoding="utf-8"))
            self._check(checks, "manifest_schema", isinstance(manifest, dict))
            self._check(checks, "workflow_schema",
                        isinstance(workflow, dict) and isinstance(workflow.get("steps"), list))
        except Exception as exc:
            errors.append(f"JSON validation failed: {exc}")

        approval = workflow.get("human_approval", []) if "workflow" in locals() else []
        self._check(
            checks,
            "approval_guardrails",
            all(x in approval for x in ("external", "financial", "irreversible")),
            "external/financial/irreversible actions require human approval",
        )

        for forbidden in ("rm -rf", "format ", "diskpart", "shutdown", "reboot", "powershell -enc"):
            text = ""
            for path in project_path.rglob("*"):
                if path.is_file() and path.stat().st_size < 2_000_000:
                    try:
                        text += path.read_text(encoding="utf-8", errors="ignore").lower()
                    except Exception:
                        pass
            if forbidden in text:
                errors.append(f"forbidden pattern detected: {forbidden}")

        stack = manifest.get("stack", []) if "manifest" in locals() and isinstance(manifest, dict) else []
        for tool in stack:
            if shutil.which(tool.lower()) is None and tool.lower() not in ("official apis", "sqlite/postgresql"):
                warnings.append(f"tool not installed locally: {tool}")

        status = "failed" if errors or any(not c["passed"] for c in checks) else (
            "warnings" if warnings else "passed"
        )
        return {
            "status": status,
            "project_path": str(project_path),
            "opportunity": project.get("opportunity", {}),
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
        }

    def execute(self, action: str, payload: dict) -> QAResult:
        if action != "validate":
            return QAResult(False, {}, f"Unsupported qa-validation action: {action}")
        projects = payload.get("input", {}).get("projects", [])
        if not isinstance(projects, list):
            return QAResult(False, {}, "input.projects must be a list")

        results = [self._validate_project(project) for project in projects[:10]]
        failed = sum(r["status"] == "failed" for r in results)
        warnings = sum(r["status"] == "warnings" for r in results)

        return QAResult(True, {
            "results": results,
            "count": len(results),
            "failed": failed,
            "warnings": warnings,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "next": [{"capability": "promotion-gate", "action": "promote", "priority": 45}],
        })
