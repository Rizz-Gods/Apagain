import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

@dataclass
class SocialPlannerResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialPlanner:
    id = "social-planner"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.queue = self.root / "data" / "social_queue.json"
        self.config = self.root / "config" / "social_schedule.json"
        self.queue.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-planner"

    def _read(self, path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _save_queue(self, data):
        self.queue.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _config(self):
        data = self._read(self.config, {})
        timezone_name = str(data.get("timezone", "UTC"))
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = timezone.utc
            timezone_name = "UTC"
        return timezone_name, tz, data.get("windows", {}), int(data.get("slot_gap_minutes", 60))

    @staticmethod
    def _parse_hhmm(value: str) -> time:
        hour, minute = [int(x) for x in str(value).split(":", 1)]
        return time(hour=hour, minute=minute)

    def _candidate_slots(self, platform: str, after: datetime, used: list[datetime]):
        timezone_name, tz, windows, gap = self._config()
        slots = windows.get(platform) or windows.get("default") or ["12:00"]
        local_after = after.astimezone(tz)
        for day_offset in range(0, 8):
            local_day = (local_after + timedelta(days=day_offset)).date()
            for raw in slots:
                try:
                    local_dt = datetime.combine(local_day, self._parse_hhmm(raw), tzinfo=tz)
                except (ValueError, TypeError):
                    continue
                if local_dt <= local_after:
                    continue
                if any(abs((local_dt - item).total_seconds()) < gap * 60 for item in used):
                    continue
                yield local_dt, timezone_name

    def execute(self, action: str, payload: dict) -> SocialPlannerResult:
        source = payload.get("input", {})
        if action not in {"plan", "preview"}:
            return SocialPlannerResult(False, {}, f"Unsupported social-planner action: {action}")

        data = self._read(self.queue, {"items": []})
        now = datetime.now(timezone.utc)
        candidates = [
            item for item in data.get("items", [])
            if item.get("status") == "queued" and not item.get("due_at")
        ]
        candidates.sort(key=lambda x: (x.get("campaign_id", ""), x.get("created_at", "")))

        used = []
        for item in data.get("items", []):
            due = item.get("due_at")
            if due:
                try:
                    used.append(datetime.fromisoformat(str(due)))
                except ValueError:
                    pass

        planned = []
        for item in candidates:
            platform = str(item.get("platform", "")).lower()
            slot = next(self._candidate_slots(platform, now, used), None)
            if not slot:
                continue
            due_dt, timezone_name = slot
            used.append(due_dt)
            row = {
                "content_id": item.get("content_id"),
                "campaign_id": item.get("campaign_id"),
                "platform": platform,
                "due_at": due_dt.isoformat(),
                "timezone": timezone_name,
                "approval_status": item.get("approval", {}).get("status", "pending"),
            }
            planned.append(row)
            if action == "plan":
                item["due_at"] = due_dt.isoformat()
                item["planned_at"] = datetime.now(timezone.utc).isoformat()
                item["schedule_timezone"] = timezone_name

        if action == "plan":
            self._save_queue(data)

        return SocialPlannerResult(True, {
            "planned": planned,
            "count": len(planned),
            "approval_bypassed": False,
            "note": "Planning only assigns due_at; public execution still requires the existing approval gate.",
        })
