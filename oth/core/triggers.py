from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import now_iso


class EventTriggerEngine:
    """Turns selected kernel events into durable, policy-routed follow-up tasks."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.config_path = self.root / "config" / "triggers.json"

    def _config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"triggers": []}
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {"triggers": []}
        except (OSError, ValueError):
            return {"triggers": []}

    def _matches(self, trigger: dict[str, Any], event_kind: str, task: dict[str, Any]) -> bool:
        event = trigger.get("event", {}) or {}
        if event.get("kind") and event["kind"] != event_kind:
            return False
        if event.get("capability") and event["capability"] != task.get("capability"):
            return False
        if event.get("action") and event["action"] != task.get("action"):
            return False
        return True

    @staticmethod
    def _payload(spec: dict[str, Any], task: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
        payload = dict(spec.get("payload", {}) or {})
        source = payload.pop("input_from", None)
        if source == "event.output":
            payload["input"] = output
        elif source == "event.task":
            payload["input"] = {
                "task_id": task.get("id"),
                "capability": task.get("capability"),
                "action": task.get("action"),
                "status": task.get("status"),
            }
        elif source == "event":
            payload["input"] = {"task": task, "output": output}
        return payload

    def fire(self, kernel, event_kind: str, task: dict[str, Any], output: dict[str, Any]) -> list[str]:
        spawned: list[str] = []
        for trigger in self._config().get("triggers", []):
            if not trigger.get("enabled", True) or not self._matches(trigger, event_kind, task):
                continue
            trigger_id = str(trigger.get("id", "unnamed"))
            fire_key = f"{trigger_id}:{task.get('id')}"
            if kernel.db.trigger_fired(fire_key):
                continue
            for spec in trigger.get("tasks", []):
                child = kernel.submit(
                    str(spec["capability"]),
                    str(spec["action"]),
                    self._payload(spec, task, output),
                    int(spec.get("priority", 50)),
                )
                spawned.append(child.id)
                kernel.db.add_event(
                    task.get("id"),
                    "task.triggered",
                    {
                        "trigger_id": trigger_id,
                        "child_task_id": child.id,
                        "capability": child.capability,
                    },
                    now_iso(),
                )
            kernel.db.mark_trigger_fired(fire_key, now_iso())
        return spawned
