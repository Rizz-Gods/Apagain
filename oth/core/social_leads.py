import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class SocialLeadResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialLeadEngine:
    id = "social-leads"

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]
        self.path = self.root / "data" / "social_leads.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-leads"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"leads": [], "events": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    @classmethod
    def _intent(cls, message: str) -> tuple[str, int, list[str]]:
        text = cls._normalize(message)
        buyer = [
            "price", "pricing", "cost", "how much", "demo", "buy", "purchase",
            "interested", "need this", "can this", "how do i start", "book",
            "proposal", "trial", "available",
        ]
        curiosity = ["what is", "how does", "curious", "tell me more", "explain"]
        support = ["bug", "error", "broken", "not working", "refund", "support"]
        buyer_hits = [x for x in buyer if x in text]
        support_hits = [x for x in support if x in text]
        curiosity_hits = [x for x in curiosity if x in text]
        if buyer_hits:
            return "buyer_intent", min(100, 65 + len(buyer_hits) * 8), buyer_hits
        if support_hits:
            return "support", 35, support_hits
        if curiosity_hits:
            return "curious", 50, curiosity_hits
        return "unclear", 20, []

    def _find_duplicate(self, leads: list[dict[str, Any]], platform: str, external_id: str, contact: str) -> dict[str, Any] | None:
        contact_key = self._normalize(contact)
        for lead in leads:
            if external_id and lead.get("platform") == platform and lead.get("external_id") == external_id:
                return lead
            if contact_key and self._normalize(lead.get("contact")) == contact_key:
                return lead
        return None
    def _upsert(self, source: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        data = self._load()
        platform = self._normalize(source.get("platform", "unknown"))
        external_id = str(source.get("external_id", "")).strip()
        contact = str(source.get("contact", "")).strip()
        message = str(source.get("message", "")).strip()
        existing = self._find_duplicate(data["leads"], platform, external_id, contact)
        intent, score, signals = self._intent(message)
        now = datetime.now(timezone.utc).isoformat()
        if existing:
            existing.update({
                "message": message or existing.get("message", ""),
                "intent": intent if score >= existing.get("score", 0) else existing.get("intent"),
                "score": max(score, existing.get("score", 0)),
                "signals": sorted(set(existing.get("signals", []) + signals)),
                "consent": bool(source.get("consent", existing.get("consent", False))),
                "content_id": str(source.get("content_id", existing.get("content_id", ""))).strip(),
                "campaign_id": str(source.get("campaign_id", existing.get("campaign_id", ""))).strip(),
                "updated_at": now,
            })
            data["events"].append({"type": "updated", "lead_id": existing["id"], "at": now})
            self._save(data)
            return existing, False
        lead = {
            "id": f"lead-{len(data['leads']) + 1}",
            "platform": platform,
            "external_id": external_id,
            "name": str(source.get("name", "")).strip(),
            "handle": str(source.get("handle", "")).strip(),
            "contact": contact,
            "message": message,
            "content_id": str(source.get("content_id", "")).strip(),
            "campaign_id": str(source.get("campaign_id", "")).strip(),
            "intent": intent,
            "score": score,
            "signals": signals,
            "consent": bool(source.get("consent", False)),
            "status": "new",
            "created_at": now,
            "updated_at": now,
        }
        data["leads"].append(lead)
        data["events"].append({"type": "created", "lead_id": lead["id"], "at": now})
        self._save(data)
        return lead, True

    def execute(self, action: str, payload: dict) -> SocialLeadResult:
        source = payload.get("input", {})
        if action == "ingest":
            lead, created = self._upsert(source)
            return SocialLeadResult(True, {
                "lead": lead,
                "created": created,
                "followup_allowed": bool(lead["consent"]),
            })
        if action == "list":
            data = self._load()
            status = source.get("status")
            leads = [x for x in data["leads"] if not status or x.get("status") == status]
            return SocialLeadResult(True, {"leads": leads})
        if action in {"qualify", "convert"}:
            data = self._load()
            lead = next((x for x in data["leads"] if x["id"] == source.get("lead_id")), None)
            if not lead:
                return SocialLeadResult(False, {}, "Unknown lead")
            lead["status"] = "qualified" if action == "qualify" else "converted"
            lead["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(data)
            return SocialLeadResult(True, {"lead": lead})

        if action == "summary":
            data = self._load()
            grouped: dict[str, dict[str, Any]] = {}
            for lead in data["leads"]:
                key = lead.get("content_id") or "unattributed"
                row = grouped.setdefault(key, {
                    "content_id": key,
                    "leads": 0,
                    "qualified_leads": 0,
                    "conversions": 0,
                })
                row["leads"] += 1
                if lead.get("status") in {"qualified", "converted"}:
                    row["qualified_leads"] += 1
                if lead.get("status") == "converted":
                    row["conversions"] += 1
            return SocialLeadResult(True, {
                "content_summary": list(grouped.values()),
                "next": [{
                    "capability": "social-optimization",
                    "action": "ingest_funnel",
                    "priority": 66,
                }],
            })

        if action == "followup_draft":
            data = self._load()
            lead = next((x for x in data["leads"] if x["id"] == source.get("lead_id")), None)
            if not lead:
                return SocialLeadResult(False, {}, "Unknown lead")
            if not lead.get("consent"):
                return SocialLeadResult(False, {}, "Follow-up blocked because consent is not recorded")
            draft = (
                f"Thanks for reaching out. Based on what you mentioned, the useful next step "
                f"is to map the workflow behind your problem and see whether the proposed offer "
                f"actually fits. Want to share how you handle it today?"
            )
            return SocialLeadResult(True, {
                "lead_id": lead["id"],
                "intent": lead["intent"],
                "score": lead["score"],
                "draft": draft,
                "approval": "required_before_external_send",
            })
        return SocialLeadResult(False, {}, f"Unsupported social-leads action: {action}")
