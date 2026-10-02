import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class BuildResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class AutomationBuilder:
    id = "automation-builder"

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]

    def supports(self, capability: str) -> bool:
        return capability == "automation-build"

    @staticmethod
    def _slug(text: str) -> str:
        text = re.sub(r"[^A-Za-z0-9]+", "-", text.lower()).strip("-")
        return text[:64] or "automation"

    @staticmethod
    def _manifest(blueprint: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": 1,
            "title": blueprint.get("title", ""),
            "problem": blueprint.get("problem", ""),
            "automation": blueprint.get("automation", ""),
            "workflow": blueprint.get("workflow", []),
            "stack": blueprint.get("stack", []),
            "complexity": blueprint.get("estimated_complexity", "unknown"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _write_project(self, root: Path, blueprint: dict[str, Any]) -> Path:
        slug = self._slug(blueprint.get("title", "automation"))
        project = root / "businesses" / slug
        project.mkdir(parents=True, exist_ok=True)
        manifest = self._manifest(blueprint)
        (project / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        workflow = "\n".join(
            f"{i+1}. {step}" for i, step in enumerate(blueprint.get("workflow", []))
        )
        readme = (
            f"# {blueprint.get('title','Automation')}\n\n"
            f"## Problem\n{blueprint.get('problem','')}\n\n"
            f"## Automation\n{blueprint.get('automation','')}\n\n"
            f"## Workflow\n{workflow}\n\n"
            f"## Stack\n" +
            "\n".join(f"- {s}" for s in blueprint.get("stack", [])) +
            "\n"
        )
        (project / "README.md").write_text(readme, encoding="utf-8")
        (project / "workflow.json").write_text(
            json.dumps({
                "name": blueprint.get("title", "Automation"),
                "trigger": "event",
                "steps": blueprint.get("workflow", []),
                "human_approval": ["external", "financial", "irreversible"],
            }, indent=2),
            encoding="utf-8",
        )
        return project

    def execute(self, action: str, payload: dict) -> BuildResult:
        if action != "build":
            return BuildResult(False, {}, f"Unsupported automation-build action: {action}")
        blueprints = payload.get("input", {}).get("blueprints", [])
        if not isinstance(blueprints, list):
            return BuildResult(False, {}, "input.blueprints must be a list")
        projects = []
        rejected = []
        for item in blueprints[:5]:
            quality = float(item.get("quality", 0.0) or 0.0)
            score = item.get("score", {}) or {}
            viability = float(score.get("score", 0.0) or 0.0)
            if quality < 0.65 or viability < 65:
                rejected.append({
                    "title": item.get("title", ""),
                    "quality": quality,
                    "viability": viability,
                    "reason": "candidate_quality_gate",
                })
                continue
            blueprint = item.get("blueprint", item)
            project = self._write_project(self.root, blueprint)
            projects.append({
                "project_path": str(project),
                "title": blueprint.get("title", ""),
                "manifest": self._manifest(blueprint),
                "opportunity": {
                    "source": item.get("source"),
                    "url": item.get("url"),
                    "query": item.get("query"),
                },
            })
        return BuildResult(True, {
            "projects": projects,
            "count": len(projects),
            "rejected": rejected,
            "next": [{"capability": "qa-validation", "action": "validate", "priority": 50}],
        })
