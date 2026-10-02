import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class SocialMarketResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialMarketWorker:
    id = "social-market"

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]
        self.config_path = self.root / "config" / "social_platforms.json"
        self.workflow_root = self.root / "workflows" / "social"
        self.platforms = self._load_platforms()

    def _load_platforms(self) -> dict[str, Any]:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return data.get("platforms", {})
        except Exception:
            return {}

    def supports(self, capability: str) -> bool:
        return capability == "social-market"

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "market"

    def _build_workflows(self, market: str, offer: str) -> list[dict[str, Any]]:
        base = [
            {
                "id": "social-signal-research",
                "goal": "Find recurring buyer pain, language, objections, and content angles.",
                "steps": ["research audience discussions", "cluster pain points", "extract buyer language", "score intent"],
            },
            {
                "id": "social-content-engine",
                "goal": "Turn validated pain into platform-native content.",
                "steps": ["select high-intent pain", "draft platform-specific content", "generate media brief", "review claims", "schedule or queue publication"],
            },
            {
                "id": "social-engagement-triage",
                "goal": "Turn inbound attention into conversations without spam.",
                "steps": ["collect mentions/comments/inbound messages", "classify intent", "draft helpful response", "request approval when needed", "record conversation state"],
            },
            {
                "id": "social-lead-funnel",
                "goal": "Convert qualified inbound interest into an owned lead.",
                "steps": ["detect buyer intent", "offer relevant resource or next step", "capture opt-in contact", "deduplicate lead", "score lead", "route to CRM"],
            },
            {
                "id": "social-followup",
                "goal": "Follow up with opted-in leads using contextual value, not bulk outreach.",
                "steps": ["check consent and recency", "select next useful touch", "draft personalized follow-up", "request approval for sensitive actions", "log outcome"],
            },
            {
                "id": "social-analytics-loop",
                "goal": "Learn what produces qualified attention and improve the next content cycle.",
                "steps": ["collect reach and engagement", "attribute leads to content", "measure qualified conversion", "compare experiments", "write next-cycle recommendations"],
            },
        ]
        return base

    def execute(self, action: str, payload: dict) -> SocialMarketResult:
        if action not in {"plan", "design"}:
            return SocialMarketResult(False, {}, f"Unsupported social-market action: {action}")

        source = payload.get("input", {})
        market = str(source.get("market", "target market")).strip()
        offer = str(source.get("offer", "product or service")).strip()
        requested = source.get("platforms") or list(self.platforms.keys())
        platforms = [p for p in requested if p in self.platforms]
        if not platforms:
            return SocialMarketResult(False, {}, "No configured social platforms were requested")

        workflows = self._build_workflows(market, offer)
        stamp = datetime.now(timezone.utc).isoformat()
        slug = self._slug(market)
        self.workflow_root.mkdir(parents=True, exist_ok=True)
        path = self.workflow_root / f"{slug}.json"
        document = {
            "version": 1,
            "market": market,
            "offer": offer,
            "platforms": platforms,
            "strategy": "inbound_first",
            "generated_at": stamp,
            "workflows": workflows,
            "platform_matrix": {
                name: self.platforms[name] for name in platforms
            },
            "human_approval": [
                "paid_campaign_launch",
                "public_claim_with_material_business_impact",
                "external_irreversible_action",
            ],
        }
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")

        project = self.root / "businesses" / f"social-market-{slug}"
        project.mkdir(parents=True, exist_ok=True)
        steps = []
        for workflow in workflows:
            steps.extend([f"{workflow['id']}: {step}" for step in workflow["steps"]])
        manifest = {
            "version": 1,
            "title": f"Social market engine: {market}",
            "problem": f"Build qualified buyer attention for {offer} in {market}.",
            "automation": "Run an inbound-first social acquisition loop from market research through content, engagement, lead capture, qualification, follow-up, and measurement.",
            "workflow": workflows,
            "stack": ["Node-RED", "Python", "official APIs", "SQLite/PostgreSQL"],
            "complexity": "medium",
            "generated_at": stamp,
        }
        (project / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        (project / "README.md").write_text(
            f"# Social market engine: {market}\n\n"
            f"Offer: {offer}\n\n"
            "This project is inbound-first and approval-gated for sensitive actions.\n",
            encoding="utf-8",
        )
        (project / "workflow.json").write_text(
            json.dumps({
                "name": manifest["title"],
                "trigger": "scheduled_or_event",
                "steps": steps,
                "human_approval": document["human_approval"],
            }, indent=2),
            encoding="utf-8",
        )
        return SocialMarketResult(True, {
            "market": market,
            "offer": offer,
            "platforms": platforms,
            "workflows": workflows,
            "workflow_path": str(path),
            "project_path": str(project),
            "projects": [{
                "project_path": str(project),
                "title": manifest["title"],
                "manifest": manifest,
            }],
            "count": len(workflows),
            "next": [{
                "capability": "workflow-compile",
                "action": "compile",
                "priority": 57,
            }],
        })
