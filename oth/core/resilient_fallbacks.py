from datetime import datetime, timezone
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FallbackResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class _BaseFallback:
    fallback = True

    def _unsupported(self, capability: str, action: str) -> FallbackResult:
        return FallbackResult(False, {"fallback": True, "capability": capability}, f"Unsupported {capability} action: {action}")


class AutomationBuilderFallback(_BaseFallback):
    id = "automation-builder-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "automation-build"

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:64] or "automation"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "build":
            return self._unsupported("automation-build", action)
        blueprints = payload.get("input", {}).get("blueprints", [])
        if not isinstance(blueprints, list):
            return FallbackResult(False, {"fallback": True}, "input.blueprints must be a list")
        projects, rejected = [], []
        for item in blueprints[:5]:
            quality = float(item.get("quality", 0) or 0)
            score = item.get("score", {}) or {}
            viability = float(score.get("score", 0) or 0)
            if quality < 0.65 or viability < 65:
                rejected.append({
                    "title": item.get("title", ""),
                    "quality": quality,
                    "viability": viability,
                    "reason": "candidate_quality_gate",
                })
                continue
            blueprint = dict(item.get("blueprint", item))
            title = blueprint.get("title", "Automation")
            project = self.root / "businesses" / self._slug(title)
            project.mkdir(parents=True, exist_ok=True)
            (project / "manifest.json").write_text(json.dumps({
                "version": 1,
                "title": title,
                "problem": blueprint.get("problem", ""),
                "automation": blueprint.get("automation", ""),
                "workflow": blueprint.get("workflow", []),
                "stack": blueprint.get("stack", []),
                "complexity": blueprint.get("estimated_complexity", "unknown"),
                "generator": self.id,
            }, indent=2), encoding="utf-8")
            (project / "workflow.json").write_text(json.dumps({
                "name": title,
                "trigger": "event",
                "steps": blueprint.get("workflow", []),
                "human_approval": ["external", "financial", "irreversible"],
            }, indent=2), encoding="utf-8")
            (project / "README.md").write_text(
                f"# {title}\n\n{blueprint.get('problem', '')}\n\n"
                + "\n".join(f"{i+1}. {s}" for i, s in enumerate(blueprint.get("workflow", [])))
                + "\n",
                encoding="utf-8",
            )
            projects.append({
                "project_path": str(project),
                "title": title,
                "manifest": blueprint,
                "opportunity": {
                    "source": item.get("source"),
                    "url": item.get("url"),
                    "query": item.get("query"),
                },
            })
        return FallbackResult(True, {
            "fallback": True,
            "projects": projects,
            "count": len(projects),
            "rejected": rejected,
            "next": [{"capability": "workflow-compile", "action": "compile", "priority": 52}],
        })


class QAFallback(_BaseFallback):
    id = "qa-validator-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "qa-validation"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "validate":
            return self._unsupported("qa-validation", action)
        projects = payload.get("input", {}).get("projects", [])
        if not isinstance(projects, list):
            return FallbackResult(False, {"fallback": True}, "input.projects must be a list")
        results = []
        for item in projects[:20]:
            raw = Path(str(item.get("project_path", "")))
            path = raw if raw.is_absolute() else self.root / raw
            checks = []
            for name in ("manifest.json", "workflow.json", "README.md"):
                checks.append({
                    "name": f"artifact:{name}",
                    "passed": (path / name).is_file(),
                })
            workflow_path = path / "workflow.json"
            if workflow_path.is_file():
                try:
                    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
                    checks.append({"name": "workflow_json", "passed": isinstance(workflow, dict)})
                    steps = workflow.get("steps", [])
                    checks.append({"name": "workflow_steps", "passed": isinstance(steps, list) and len(steps) > 0})
                except Exception:
                    checks.append({"name": "workflow_json", "passed": False})
            passed = all(x["passed"] for x in checks)
            results.append({
                "project_path": str(path),
                "status": "passed" if passed else "warnings",
                "passed": passed,
                "warnings": [x["name"] for x in checks if not x["passed"]],
                "checks": checks,
                "fallback": True,
                "verification_mode": "structural",
                "opportunity": item.get("opportunity", {}),
            })
        output = {"fallback": True, "results": results, "count": len(results)}
        if any(r["status"] == "warnings" for r in results):
            output["next"] = [{"capability": "dependency-provision", "action": "plan", "priority": 48}]
        return FallbackResult(True, output)


class PromotionFallback(_BaseFallback):
    id = "promotion-gate-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "promotion-gate"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "promote":
            return self._unsupported("promotion-gate", action)
        rows = payload.get("input", {}).get("results", [])
        if not isinstance(rows, list):
            return FallbackResult(False, {"fallback": True}, "input.results must be a list")
        decisions = []
        for row in rows[:20]:
            status = str(row.get("status", "failed"))
            decision = "ready" if status == "passed" else "held" if status == "warnings" else "rejected"
            decisions.append({
                "project_path": str(row.get("project_path", "")),
                "opportunity": row.get("opportunity", {}) or {},
                "status": decision,
                "reason": {
                    "ready": "Structural QA passed; eligible for promotion review",
                    "held": "Warnings present; promotion remains held",
                    "rejected": "QA failed; promotion blocked",
                }[decision],
                "fallback": True,
            })
        return FallbackResult(True, {"fallback": True, "decisions": decisions, "count": len(decisions)})


class DependencyProvisionFallback(_BaseFallback):
    id = "dependency-provisioner-fallback"
    ALLOWLIST = {
        "node-red": ("npm", "node-red"),
        "n8n": ("npm", "n8n"),
        "agent-browser": ("npm", "agent-browser"),
    }

    def supports(self, capability: str) -> bool:
        return capability == "dependency-provision"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "plan":
            return self._unsupported("dependency-provision", action)
        source = payload.get("input", {})
        warnings = list(source.get("warnings", []) or [])
        for row in source.get("results", []) or []:
            warnings.extend(row.get("warnings", []) if isinstance(row, dict) else [])
        plans = []
        seen = set()
        for warning in warnings:
            text = str(warning).lower()
            for name, (manager, binary) in self.ALLOWLIST.items():
                if name in text and name not in seen:
                    seen.add(name)
                    plans.append({
                        "dependency": name,
                        "installed": bool(shutil.which(f"{binary}.cmd") or shutil.which(binary)),
                        "manager": manager,
                        "action": "install",
                        "mode": "plan-only",
                    })
        return FallbackResult(True, {"fallback": True, "plans": plans, "count": len(plans)})


class WorkflowCompilerFallback(_BaseFallback):
    id = "workflow-compiler-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "workflow-compile"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "compile":
            return self._unsupported("workflow-compile", action)
        projects = payload.get("input", {}).get("projects", [])
        if not isinstance(projects, list):
            return FallbackResult(False, {"fallback": True}, "input.projects must be a list")
        compiled = []
        for item in projects[:10]:
            raw = Path(str(item.get("project_path", "")))
            path = raw if raw.is_absolute() else self.root / raw
            workflow = json.loads((path / "workflow.json").read_text(encoding="utf-8"))
            steps = workflow.get("steps", [])
            draft = {
                "name": workflow.get("name", "OTH Automation"),
                "trigger": workflow.get("trigger", "event"),
                "steps": steps,
                "active": False,
                "generated_by": self.id,
                "provider_neutral": True,
            }
            target = path / "oth.workflow.fallback.json"
            target.write_text(json.dumps(draft, indent=2), encoding="utf-8")
            compiled.append({
                "project_path": str(path),
                "workflow_path": str(target),
                "workflow_name": draft["name"],
                "nodes": len(steps) + 1,
                "active": False,
                "provider_neutral": True,
                "opportunity": item.get("opportunity", {}),
            })
        return FallbackResult(True, {
            "fallback": True,
            "compiled": compiled,
            "count": len(compiled),
            "next": [{"capability": "qa-validation", "action": "validate", "priority": 50}],
        })


class MediaQAFallback(_BaseFallback):
    id = "media-qa-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "media-qa"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "check":
            return self._unsupported("media-qa", action)
        source = payload.get("input", {})
        media_ref = str(source.get("media_ref", "")).strip()
        if not media_ref:
            return FallbackResult(False, {"fallback": True}, "media_ref is required")
        raw = Path(media_ref).expanduser()
        path = raw if raw.is_absolute() else self.root / raw
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(self.root.resolve()):
            return FallbackResult(False, {"fallback": True}, "media_ref must resolve inside the OTH workspace")
        suffix = path.suffix.lower()
        supported = suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".wav", ".mp3", ".m4a"}
        issues = [] if supported else ["unsupported_media_extension"]
        if path.stat().st_size == 0:
            issues.append("empty_media")
        return FallbackResult(True, {
            "fallback": True,
            "media_ref": str(path.relative_to(self.root)),
            "size_bytes": path.stat().st_size,
            "format": suffix.lstrip("."),
            "issues": issues,
            "passed": not issues,
            "verification_mode": "filesystem-structural",
        })


class MediaTranscriptionFallback(_BaseFallback):
    id = "media-transcription-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.out_dir = self.root / "data" / "media" / "captions"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "media-transcription"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action != "transcribe":
            return self._unsupported("media-transcription", action)
        source = payload.get("input", {})
        media_ref = str(source.get("media_ref", "")).strip()
        text = str(source.get("transcript_text", "")).strip()
        if not media_ref:
            return FallbackResult(False, {"fallback": True}, "media_ref is required")
        if not text:
            sidecar = Path(media_ref).expanduser()
            if not sidecar.is_absolute():
                sidecar = self.root / sidecar
            sidecar = sidecar.with_suffix(".txt")
            if sidecar.is_file():
                text = sidecar.read_text(encoding="utf-8").strip()
        if not text:
            return FallbackResult(False, {"fallback": True, "mode": "sidecar-import"}, "No transcript backend or sidecar text available", retryable=True)
        words = text.split()
        duration = float(source.get("duration_seconds", 0) or 0)
        end = max(duration, 1.0)
        srt_path = self.out_dir / f"{Path(media_ref).stem}.fallback.srt"
        srt_path.write_text(f"1\n00:00:00,000 --> 00:00:{int(end):02},000\n{text}\n", encoding="utf-8")
        return FallbackResult(True, {
            "fallback": True,
            "mode": "sidecar-import",
            "media_ref": str(Path(media_ref)),
            "language": source.get("language", "unknown"),
            "duration": end,
            "segments": [{"start": 0.0, "end": end, "text": text, "words": []}],
            "srt_path": str(srt_path.relative_to(self.root)),
        })


class SocialAnalyticsFallback(_BaseFallback):
    id = "social-analytics-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_metrics.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-analytics"

    def _load(self):
        if not self.path.exists():
            return {"items": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"items": []}

    def _save(self, data):
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def execute(self, action: str, payload: dict) -> FallbackResult:
        source = payload.get("input", {})
        if action == "list":
            return FallbackResult(True, {"fallback": True, "items": self._load().get("items", [])})
        if action == "record":
            data = self._load()
            item = {
                "content_id": source.get("content_id"),
                "platform": source.get("platform"),
                "external_id": source.get("external_id", ""),
                "metrics": source.get("metrics", {}),
                "status": "manual_fallback_record",
            }
            data["items"].append(item)
            self._save(data)
            return FallbackResult(True, {"fallback": True, "record": item})
        if action == "fetch":
            metrics = source.get("metrics")
            if not isinstance(metrics, dict):
                return FallbackResult(
                    True,
                    {"fallback": True, "status": "awaiting_provider_metrics", "live": False},
                )
            item = {
                "content_id": source.get("content_id"),
                "platform": source.get("platform"),
                "external_id": source.get("external_id"),
                "metrics": metrics,
                "status": "fallback_local_metrics",
                "live": False,
            }
            return FallbackResult(True, {"fallback": True, "record": item, "next": []})
        if action == "sync":
            return FallbackResult(True, {
                "fallback": True,
                "results": [],
                "synced": 0,
                "next": [],
                "status": "provider_independent_sync_only",
            })
        return self._unsupported("social-analytics", action)


class SocialOptimizationFallback(_BaseFallback):
    id = "social-optimization-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_learning.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-optimization"

    @staticmethod
    def _score(metrics):
        impressions = max(float(metrics.get("impressions", 0) or 0), 1.0)
        engagements = float(metrics.get("engagements", 0) or 0)
        qualified = float(metrics.get("qualified_leads", 0) or 0)
        conversions = float(metrics.get("conversions", 0) or 0)
        return round(
            engagements / impressions * 100
            + qualified / impressions * 500
            + conversions / impressions * 1000, 4
        )

    def _load(self):
        if not self.path.exists():
            return {"experiments": [], "insights": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"experiments": [], "insights": []}

    def _save(self, data):
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def execute(self, action: str, payload: dict) -> FallbackResult:
        source = payload.get("input", {})
        data = self._load()
        if action == "record":
            metrics = source.get("metrics", {})
            row = {
                "platform": source.get("platform", ""),
                "content_id": source.get("content_id", ""),
                "hook": source.get("hook", ""),
                "format": source.get("format", ""),
                "pillar": source.get("pillar", ""),
                "metrics": metrics,
                "score": self._score(metrics),
                "fallback": True,
            }
            data["experiments"] = [
                x for x in data.get("experiments", [])
                if not (
                    x.get("platform") == row["platform"]
                    and x.get("content_id") == row["content_id"]
                )
            ]
            data["experiments"].append(row)
            self._save(data)
            return FallbackResult(True, {"fallback": True, "experiment": row, "status": "recorded"})
        if action == "ingest_funnel":
            updated = []
            for summary in source.get("content_summary", []) or []:
                for row in data.get("experiments", []):
                    if row.get("content_id") == summary.get("content_id"):
                        row.setdefault("metrics", {})["qualified_leads"] = summary.get("qualified_leads", 0)
                        row["metrics"]["conversions"] = summary.get("conversions", 0)
                        row["score"] = self._score(row["metrics"])
                        updated.append(row["content_id"])
            self._save(data)
            return FallbackResult(True, {"fallback": True, "updated_content_ids": updated, "synced": len(updated)})
        if action == "optimize":
            platform = source.get("platform")
            rows = [x for x in data.get("experiments", []) if not platform or x.get("platform") == platform]
            rows.sort(key=lambda x: x.get("score", 0), reverse=True)
            return FallbackResult(True, {
                "fallback": True,
                "best": rows[:5],
                "recommendations": [{
                    "type": "controlled_iteration",
                    "message": "Preserve winning combinations and vary one variable at a time.",
                }],
                "next_experiments": [
                    {"name": "hook-contrast", "change": "hook", "variant_instruction": "Try a sharper opening while preserving the proof."},
                    {"name": "format-shift", "change": "format", "variant_instruction": "Republish the winning idea in one adjacent format."},
                    {"name": "cta-friction", "change": "cta", "variant_instruction": "Reduce CTA friction while retaining buyer intent."},
                ] if rows else [],
            })
        return self._unsupported("social-optimization", action)


class SocialContentFallback(_BaseFallback):
    id = "social-content-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "social-content"

    @staticmethod
    def _hashtags(market, offer):
        tags = []
        for word in re.findall(r"[A-Za-z0-9]+", f"{market} {offer}"):
            if len(word) >= 4:
                tag = f"#{word.lower()}"
                if tag not in tags:
                    tags.append(tag)
        return tags[:5]

    def execute(self, action: str, payload: dict) -> FallbackResult:
        source = payload.get("input", {})
        if action == "list":
            return FallbackResult(True, {"fallback": True, "items": []})
        if action not in {"draft", "queue"}:
            return self._unsupported("social-content", action)
        market = str(source.get("market", "target market"))
        offer = str(source.get("offer", "offer"))
        pain = str(source.get("pain", "Manual work is consuming growth capacity."))
        proof = str(source.get("proof", "Show one concrete mechanism or result."))
        cta = str(source.get("cta", "Reply with your current workflow."))
        hook = str(source.get("hook", "")).strip() or pain
        tags = " ".join(self._hashtags(market, offer))
        variants = {
            "linkedin": {"format": "text_or_carousel", "hook": hook, "text": f"{hook}\n\n{pain}\n\n{proof}\n\n{cta}\n\n{tags}".strip()},
            "x": {"format": "text", "hook": hook, "text": f"{hook} {proof} {cta}".strip()[:280]},
            "youtube": {"format": "short_or_video", "hook": hook, "title": f"{hook[:70]} | {offer}", "description": f"{hook}\n\n{proof}\n\n{cta}".strip()},
            "instagram": {"format": "reel_or_carousel", "hook": hook, "caption": f"{hook}\n\n{pain}\n\n{proof}\n\n{cta}\n\n{tags}".strip()},
        }
        platforms = source.get("platforms") or list(variants)
        variants = {k: variants[k] for k in platforms if k in variants}
        qa = {
            "status": "passed" if variants else "failed",
            "errors": [] if variants else ["no_supported_platforms"],
            "warnings": ["fallback_copy_needs_human_review"],
        }
        package = {
            "version": 1,
            "campaign_id": source.get("campaign_id", ""),
            "market": market,
            "offer": offer,
            "pain": pain,
            "proof": proof,
            "cta": cta,
            "hook": hook,
            "variants": variants,
            "qa": qa,
            "claim_check": {"required": True, "status": "pending"},
            "generated_by": self.id,
        }
        queued = [{
            "content_id": f"fallback-{platform}-{index}",
            "platform": platform,
            "payload": variant,
            "status": "queued",
            "approval": {"required": True, "status": "pending"},
        } for index, (platform, variant) in enumerate(variants.items(), 1)] if action == "queue" else []
        return FallbackResult(True, {
            "fallback": True,
            "package": package,
            "queued": queued,
            "next": [],
        })


class SocialPlannerFallback(_BaseFallback):
    id = "social-planner-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "social-planner"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action not in {"plan", "preview"}:
            return self._unsupported("social-planner", action)
        source = payload.get("input", {})
        now = datetime.now(timezone.utc)
        items = source.get("items") or []
        planned = []
        for index, item in enumerate(items[:50]):
            platform = str(item.get("platform", "default")).lower()
            due = now + __import__("datetime").timedelta(minutes=30 * (index + 1))
            planned.append({
                "content_id": item.get("content_id"),
                "campaign_id": item.get("campaign_id"),
                "platform": platform,
                "due_at": due.isoformat(),
                "timezone": "UTC",
                "approval_status": item.get("approval", {}).get("status", "pending"),
            })
        return FallbackResult(True, {
            "fallback": True,
            "planned": planned,
            "count": len(planned),
            "approval_bypassed": False,
            "note": "Fallback planner uses provider-neutral UTC slots; it never approves publication.",
        })


class SocialEditorialFallback(_BaseFallback):
    id = "social-editor-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "social-editor"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action not in {"brief", "plan", "review"}:
            return self._unsupported("social-editor", action)
        source = payload.get("input", {})
        if action == "review":
            return FallbackResult(True, {"fallback": True, "briefs": [], "revisions": []})
        campaign = source.get("campaign") or {}
        platforms = source.get("platforms") or ["linkedin", "x", "youtube", "instagram"]
        pain = str(campaign.get("pain", "the problem"))
        proof = str(campaign.get("proof", "one concrete proof point"))
        briefs = []
        for platform in platforms:
            p = str(platform).lower()
            fmt = {"youtube": "short", "instagram": "reel", "linkedin": "carousel_or_text"}.get(p, "text_or_visual")
            briefs.append({
                "brief_id": f"fallback-{campaign.get('campaign_id', 'campaign')}-{p}",
                "campaign_id": campaign.get("campaign_id"),
                "platform": p,
                "purpose": source.get("purpose", "discovery"),
                "funnel_stage": source.get("funnel_stage", "awareness"),
                "format": fmt,
                "duration_seconds": 30 if p in {"youtube", "instagram"} else 0,
                "hook": pain,
                "claim": pain,
                "proof": proof,
                "sources": source.get("sources") or ["campaign brief"],
                "edit_recipe": ["open on pain", "show mechanism", "show proof", "end with one CTA"],
                "status": "ready_for_production",
                "fallback": True,
            })
        return FallbackResult(True, {
            "fallback": True,
            "briefs": briefs,
            "count": len(briefs),
            "next": [],
        })
