import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class OptimizationResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialOptimizer:
    id = "social-optimizer"

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]
        self.path = self.root / "data" / "social_learning.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-optimization"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"experiments": [], "insights": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _score(metrics: dict[str, Any]) -> float:
        impressions = max(float(metrics.get("impressions", 0)), 1.0)
        engagement = float(metrics.get("engagements", 0))
        qualified = float(metrics.get("qualified_leads", 0))
        conversions = float(metrics.get("conversions", 0))
        return round(
            (engagement / impressions) * 100
            + (qualified / impressions) * 500
            + (conversions / impressions) * 1000,
            4,
        )

    def execute(self, action: str, payload: dict) -> OptimizationResult:
        source = payload.get("input", {})
        data = self._load()
        if action == "ingest_funnel":
            summaries = source.get("content_summary", [])
            updated = []
            for summary in summaries:
                content_id = summary.get("content_id")
                for experiment in data["experiments"]:
                    if content_id and experiment.get("content_id") == content_id:
                        metrics = experiment.setdefault("metrics", {})
                        metrics["qualified_leads"] = float(summary.get("qualified_leads", 0))
                        metrics["conversions"] = float(summary.get("conversions", 0))
                        experiment["score"] = self._score(metrics)
                        updated.append(content_id)
            data.setdefault("funnel_sync", []).append({
                "content_summary": summaries,
                "updated": updated,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            })
            self._save(data)
            return OptimizationResult(True, {
                "updated_content_ids": updated,
                "synced": len(summaries),
            })
        if action == "record":
            metrics = source.get("metrics", {})
            experiment = {
                "platform": source.get("platform", ""),
                "content_id": source.get("content_id", ""),
                "hook": source.get("hook", ""),
                "format": source.get("format", ""),
                "pillar": source.get("pillar", ""),
                "metrics": metrics,
                "score": self._score(metrics),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            data["experiments"].append(experiment)
            self._save(data)
            return OptimizationResult(True, {"experiment": experiment})
        if action == "optimize":
            platform = source.get("platform")
            rows = [
                x for x in data["experiments"]
                if not platform or x.get("platform") == platform
            ]
            rows.sort(key=lambda x: x.get("score", 0), reverse=True)
            leaders = rows[:5]
            recommendations = []
            experiments = []
            if leaders:
                winner = leaders[0]
                recommendations.append({
                    "type": "repeat_strength",
                    "message": "Preserve the strongest hook/format/pillar combinations and test one variable at a time.",
                    "examples": [
                        {"hook": x["hook"], "format": x["format"], "pillar": x["pillar"], "score": x["score"]}
                        for x in leaders
                    ],
                })
                experiments = [
                    {
                        "name": "hook-contrarian",
                        "change": "hook",
                        "base": winner["hook"],
                        "variant_instruction": "Rewrite the opening as a contrarian claim while preserving the same problem and proof.",
                    },
                    {
                        "name": "hook-proof",
                        "change": "hook",
                        "base": winner["hook"],
                        "variant_instruction": "Rewrite the opening around a concrete result or quantified proof.",
                    },
                    {
                        "name": "cta-conversion",
                        "change": "cta",
                        "base": winner["hook"],
                        "variant_instruction": "Keep the winning hook and format, but use a low-friction buyer-intent CTA tied to the offer.",
                    },
                ]
            recommendations.append({
                "type": "conversion_priority",
                "message": "Optimize for qualified leads and conversions, not raw reach alone.",
            })
            recommendations.append({
                "type": "exploration",
                "message": "Run controlled variants of the current leaders so OTH improves without blindly changing what already works.",
            })
            insight = {
                "platform": platform or "all",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "recommendations": recommendations,
            }
            data["insights"].append(insight)
            self._save(data)
            return OptimizationResult(True, {
                "best": leaders,
                "recommendations": recommendations,
                "next_experiments": experiments,
            })
        return OptimizationResult(False, {}, f"Unsupported social-optimization action: {action}")
