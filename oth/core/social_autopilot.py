import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oth.core.db import Database
from oth.core.social_content import SocialContentEngine

@dataclass
class SocialAutopilotResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialAutopilot:
    id = "social-autopilot"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.state_path = self.root / "data" / "social_autopilot.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-autopilot"

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"campaigns": [], "runs": []}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "opportunity"

    def _learning_hint(self, platforms: list[str]) -> dict[str, Any]:
        path = self.root / "data" / "social_learning.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        experiments = [
            x for x in data.get("experiments", [])
            if x.get("hook") and (not platforms or x.get("platform") in platforms)
        ]
        if not experiments:
            return {}
        experiments.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
        best = experiments[0]
        return {
            "hook": best.get("hook", ""),
            "pillar": best.get("pillar", "acquisition"),
            "format": best.get("format", ""),
            "source_content_id": best.get("content_id"),
            "source_platform": best.get("platform"),
            "source_score": best.get("score"),
        }

    def _candidate(self, row) -> dict[str, Any]:
        title = str(row["title"] or row["query"] or "Untitled opportunity")
        query = str(row["query"] or title)
        snippet = str(row["snippet"] or "")
        slug = self._slug(title)
        manifest_path = self.root / "businesses" / f"automation-blueprint-{slug}" / "manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
        problem = str(manifest.get("problem") or snippet or f"Buyers are actively looking for better solutions around {query}.")
        offer = f"Automation workflow for {str(manifest.get('title') or title)}"
        proof = str(manifest.get("automation") or "Start with the repetitive intake, processing, notification, and logging steps identified by OTH.")
        cta = "Describe how you handle this today and OTH can map the first workflow worth automating."
        return {
            "opportunity_id": int(row["id"]),
            "campaign_id": f"opportunity-{row['id']}-{self._slug(title)}",
            "market": title,
            "offer": offer,
            "pain": problem,
            "proof": proof,
            "cta": cta,
            "score": float(row["score"] or 0),
            "query": query,
            "source": row["source"],
        }
    def execute(self, action: str, payload: dict) -> SocialAutopilotResult:
        if action not in {"run", "status"}:
            return SocialAutopilotResult(False, {}, f"Unsupported social-autopilot action: {action}")

        state = self._load()
        if action == "status":
            return SocialAutopilotResult(True, {
                "campaigns": state["campaigns"],
                "runs": state["runs"][-10:],
            })

        source = payload.get("input", {})
        min_score = float(source.get("min_score", 65))
        max_new = int(source.get("max_new_campaigns", 1))
        platforms = source.get("platforms") or ["linkedin", "x", "youtube", "instagram"]
        learning_hint = self._learning_hint(platforms)
        processed = {
            c.get("opportunity_id")
            for c in state["campaigns"]
            if c.get("status") in {"queued_for_review", "active"}
        }

        db = Database(self.root / "data" / "oth.db")
        try:
            rows = db.top_opportunities(max(10, max_new * 5))
        finally:
            db.close()

        created = []
        skipped = []
        content = SocialContentEngine(self.root)
        for row in rows:
            opportunity_id = int(row["id"])
            score = float(row["score"] or 0)
            if score < min_score:
                skipped.append({"opportunity_id": opportunity_id, "reason": "below_threshold", "score": score})
                continue
            if opportunity_id in processed:
                skipped.append({"opportunity_id": opportunity_id, "reason": "already_processed"})
                continue
            if len(created) >= max_new:
                break

            campaign = self._candidate(row)
            package = content.execute("queue", {
                "input": {
                    "campaign_id": campaign["campaign_id"],
                    "market": campaign["market"],
                    "offer": campaign["offer"],
                    "pain": campaign["pain"],
                    "proof": campaign["proof"],
                    "cta": campaign["cta"],
                    "hook": learning_hint.get("hook", campaign["pain"]),
                    "pillar": learning_hint.get("pillar", "acquisition"),
                    "auto_compact": True,
                    "platforms": platforms,
                }
            })
            if not package.success:
                return SocialAutopilotResult(False, {}, package.error)

            queued = package.output.get("queued", [])
            campaign_record = {
                **campaign,
                "platforms": platforms,
                "content_ids": [item["content_id"] for item in queued],
                "status": "queued_for_review",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "learning_reference": learning_hint,
            }
            state["campaigns"].append(campaign_record)
            created.append(campaign_record)

        run = {
            "created": len(created),
            "skipped": len(skipped),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        state["runs"].append(run)
        self._save(state)
        return SocialAutopilotResult(True, {
            "created_campaigns": created,
            "skipped": skipped,
            "learning_reference": learning_hint,
            "next": [{
                "capability": "social-leads",
                "action": "summary",
                "priority": 64,
            }],
        })
