import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class SocialControlResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialControl:
    id = "social-control"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.autopilot = self.root / "data" / "social_autopilot.json"
        self.queue = self.root / "data" / "social_queue.json"
        self.leads = self.root / "data" / "social_leads.json"
        self.learning = self.root / "data" / "social_learning.json"

    def supports(self, capability: str) -> bool:
        return capability == "social-control"

    def _read(self, path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def execute(self, action: str, payload: dict) -> SocialControlResult:
        if action not in {"status", "attention"}:
            return SocialControlResult(False, {}, f"Unsupported social-control action: {action}")

        campaigns = self._read(self.autopilot, {"campaigns": []}).get("campaigns", [])
        items = self._read(self.queue, {"items": []}).get("items", [])
        leads = self._read(self.leads, {"leads": []}).get("leads", [])
        learning = self._read(self.learning, {"experiments": [], "insights": []})

        now = datetime.now(timezone.utc)
        by_campaign = {}
        for item in items:
            key = item.get("campaign_id") or "unassigned"
            row = by_campaign.setdefault(key, {
                "campaign_id": key,
                "content": 0,
                "queued": 0,
                "waiting_credentials": 0,
                "dispatching": 0,
                "published": 0,
                "failed": 0,
                "awaiting_approval": 0,
                "scheduled": 0,
                "next_due_at": None,
            })
            row["content"] += 1
            status = item.get("status", "queued")
            if status in row:
                row[status] += 1
            if item.get("approval", {}).get("status") == "pending":
                row["awaiting_approval"] += 1
            due_at = item.get("due_at")
            if due_at and status == "queued":
                try:
                    due_time = datetime.fromisoformat(str(due_at))
                    if due_time > now:
                        row["scheduled"] += 1
                        if not row["next_due_at"] or due_time < datetime.fromisoformat(row["next_due_at"]):
                            row["next_due_at"] = due_time.isoformat()
                except (TypeError, ValueError):
                    pass

        lead_by_campaign = {}
        for lead in leads:
            key = lead.get("campaign_id") or "unattributed"
            row = lead_by_campaign.setdefault(key, {"leads": 0, "qualified": 0, "conversions": 0})
            row["leads"] += 1
            if lead.get("status") in {"qualified", "converted"}:
                row["qualified"] += 1
            if lead.get("status") == "converted":
                row["conversions"] += 1

        report = []
        for campaign in campaigns:
            cid = campaign.get("campaign_id")
            row = {
                "campaign_id": cid,
                "market": campaign.get("market"),
                "score": campaign.get("score"),
                "status": campaign.get("status"),
                "platforms": campaign.get("platforms", []),
                "queue": by_campaign.get(cid, {}),
                "funnel": lead_by_campaign.get(cid, {"leads": 0, "qualified": 0, "conversions": 0}),
                "created_at": campaign.get("created_at"),
            }
            report.append(row)

        attention = []
        for row in report:
            queue = row.get("queue", {})
            if queue.get("awaiting_approval", 0):
                attention.append({
                    "campaign_id": row["campaign_id"],
                    "priority": "human_review",
                    "reason": "content_waiting_for_approval",
                    "count": queue["awaiting_approval"],
                })
            if queue.get("waiting_credentials", 0):
                attention.append({
                    "campaign_id": row["campaign_id"],
                    "priority": "credential",
                    "reason": "provider_credentials_missing",
                    "count": queue["waiting_credentials"],
                })
            if queue.get("failed", 0):
                attention.append({
                    "campaign_id": row["campaign_id"],
                    "priority": "recovery",
                    "reason": "published_action_failed",
                    "count": queue["failed"],
                })

        snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "campaigns": report,
            "attention": attention,
            "totals": {
                "campaigns": len(report),
                "content_items": len(items),
                "leads": len(leads),
                "qualified_leads": sum(1 for x in leads if x.get("status") in {"qualified", "converted"}),
                "conversions": sum(1 for x in leads if x.get("status") == "converted"),
                "experiments": len(learning.get("experiments", [])),
            },
        }
        return SocialControlResult(True, snapshot)
