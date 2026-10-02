import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class CompileResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class WorkflowCompiler:
    id = "workflow-compiler"

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]

    def supports(self, capability: str) -> bool:
        return capability == "workflow-compile"

    @staticmethod
    def _node_id() -> str:
        return str(uuid.uuid4())

    def _compile_project(self, project: dict) -> dict:
        project_path = Path(project.get("project_path", ""))
        if not project_path.is_absolute():
            project_path = self.root / project_path

        manifest_path = project_path / "manifest.json"
        workflow_path = project_path / "workflow.json"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        abstract = json.loads(workflow_path.read_text(encoding="utf-8"))

        nodes = []
        connections = {}

        trigger_id = self._node_id()
        trigger_name = "OTH Trigger"
        nodes.append({
            "parameters": {},
            "id": trigger_id,
            "name": trigger_name,
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [0, 0],
        })
        previous = trigger_name

        for index, step in enumerate(abstract.get("steps", []), start=1):
            name = f"OTH Step {index}"
            node_id = self._node_id()
            nodes.append({
                "parameters": {
                    "jsCode": (
                        "return [{ json: { "
                        f"step: {json.dumps(step)}, "
                        "status: 'placeholder', "
                        "note: 'Replace this compiler placeholder with the "
                        "domain-specific node or agent action.' "
                        "} }];"
                    )
                },
                "id": node_id,
                "name": name,
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [index * 260, 0],
            })
            connections.setdefault(previous, {"main": [[]]})
            connections[previous]["main"][0].append({
                "node": name,
                "type": "main",
                "index": 0,
            })
            previous = name

        compiled = {
            "name": manifest.get("title", "OTH Automation"),
            "nodes": nodes,
            "pinData": {},
            "connections": connections,
            "active": False,
            "settings": {},
            "versionId": str(uuid.uuid4()),
            "meta": {"othGenerated": True},
            "tags": [],
        }

        target = project_path / "n8n.workflow.json"
        target.write_text(json.dumps(compiled, indent=2), encoding="utf-8")

        return {
            "project_path": str(project_path),
            "workflow_path": str(target),
            "workflow_name": compiled["name"],
            "nodes": len(nodes),
            "active": False,
            "opportunity": project.get("opportunity", {}),
        }

    def execute(self, action: str, payload: dict) -> CompileResult:
        if action != "compile":
            return CompileResult(False, {}, f"Unsupported workflow-compile action: {action}")
        projects = payload.get("input", {}).get("projects", [])
        if not isinstance(projects, list):
            return CompileResult(False, {}, "input.projects must be a list")

        compiled = [self._compile_project(project) for project in projects[:10]]
        return CompileResult(True, {
            "compiled": compiled,
            "count": len(compiled),
            "next": [{"capability": "qa-validation", "action": "validate", "priority": 50}],
        })
