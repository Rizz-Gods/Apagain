import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class SocialQueueResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialQueueManager:
    id = "social-queue"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_queue.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-queue"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"items": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _find(self, data, content_id):
        return next((x for x in data["items"] if x.get("content_id") == content_id or x.get("id") == content_id), None)

    def execute(self, action: str, payload: dict) -> SocialQueueResult:
        source = payload.get("input", {})
        data = self._load()

        if action == "list":
            status = source.get("status")
            platform = source.get("platform")
            items = [
                x for x in data["items"]
                if (not status or x.get("status") == status)
                and (not platform or x.get("platform") == platform)
            ]
            return SocialQueueResult(True, {"items": items})

        if action == "approve":
            item = self._find(data, str(source.get("content_id", "")))
            if not item:
                return SocialQueueResult(False, {}, "Unknown content item")
            if item.get("status") in {"published", "publishing"}:
                return SocialQueueResult(False, {}, "Content item is already in execution")
            item["approval"] = {
                "required": True,
                "status": "approved",
                "approved_by": str(source.get("approved_by", "operator")),
                "approved_at": self._now(),
            }
            item["status"] = "queued"
            item["updated_at"] = self._now()
            self._save(data)
            return SocialQueueResult(True, {"item": item})

        if action == "reject":
            item = self._find(data, str(source.get("content_id", "")))
            if not item:
                return SocialQueueResult(False, {}, "Unknown content item")
            item["approval"] = {
                "required": True,
                "status": "rejected",
                "reason": str(source.get("reason", "operator_rejected")),
                "rejected_at": self._now(),
            }
            item["status"] = "rejected"
            item["updated_at"] = self._now()
            self._save(data)
            return SocialQueueResult(True, {"item": item})

        if action == "schedule":
            item = self._find(data, str(source.get("content_id", "")))
            if not item:
                return SocialQueueResult(False, {}, "Unknown content item")
            due_at = source.get("due_at")
            if due_at:
                try:
                    datetime.fromisoformat(str(due_at))
                except ValueError:
                    return SocialQueueResult(False, {}, "due_at must be a valid ISO-8601 timestamp")
            item["due_at"] = str(due_at) if due_at else None
            item["status"] = "queued"
            item["last_error"] = None
            item["updated_at"] = self._now()
            self._save(data)
            return SocialQueueResult(True, {"item": item})

        if action == "requeue":
            item = self._find(data, str(source.get("content_id", "")))
            if not item:
                return SocialQueueResult(False, {}, "Unknown content item")
            if item.get("approval", {}).get("status") != "approved":
                return SocialQueueResult(False, {}, "Requeue requires prior approval")
            item["status"] = "queued"
            item["last_error"] = None
            item["updated_at"] = self._now()
            self._save(data)
            return SocialQueueResult(True, {"item": item})

        if action == "reconcile":
            dispatches = []
            held = []
            now = datetime.now(timezone.utc)
            for item in data["items"]:
                status = item.get("status", "queued")
                approval = item.get("approval", {}).get("status", "pending")

                if status == "dispatching":
                    updated = item.get("updated_at")
                    try:
                        age = (now - datetime.fromisoformat(updated)).total_seconds()
                    except Exception:
                        age = 0
                    if age > 900:
                        item["status"] = "queued"
                        item["last_error"] = "stale_dispatch_recovered"
                        item["updated_at"] = now.isoformat()
                        status = "queued"
                    else:
                        continue

                if status not in {"queued", "waiting_credentials", "failed"}:
                    continue
                due_at = item.get("due_at")
                if due_at:
                    try:
                        due_time = datetime.fromisoformat(str(due_at))
                    except ValueError:
                        item["last_error"] = "invalid_due_at"
                        continue
                    if due_time > now:
                        continue
                if approval != "approved":
                    if status == "queued":
                        held.append({"content_id": item.get("content_id"), "reason": "awaiting_approval"})
                    continue

                item["status"] = "dispatching"
                item["updated_at"] = now.isoformat()
                dispatches.append({
                    "capability": "social-actions",
                    "action": "publish_text",
                    "priority": 76,
                    "payload": {
                        "risk": "external",
                        "approved": True,
                        "approved_by": approval,
                        "input": {
                            "provider": item.get("platform"),
                            "text": (
                                item.get("payload", {}).get("text")
                                or item.get("payload", {}).get("caption")
                                or item.get("payload", {}).get("description")
                                or ""
                            ),
                            "title": item.get("payload", {}).get("title"),
                            "description": item.get("payload", {}).get("description"),
                            "content_id": item.get("content_id"),
                            "campaign_id": item.get("campaign_id"),
                        },
                    },
                    "content_id": item.get("content_id"),
                })

            self._save(data)
            return SocialQueueResult(True, {
                "dispatches": dispatches,
                "held": held,
                "checked": len(data["items"]),
                "scheduled": sum(1 for item in data["items"] if item.get("due_at") and item.get("status") == "queued"),
                "next": dispatches,
            })

        return SocialQueueResult(False, {}, f"Unsupported social-queue action: {action}")
