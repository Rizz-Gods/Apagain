import hashlib
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

class MediaAssetsFallback(_BaseFallback):
    id = "media-assets-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.registry_path = self.root / "data" / "media_assets_fallback.json"
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "media-assets"

    def _load(self):
        if not self.registry_path.exists():
            return {"assets": []}
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception:
            return {"assets": []}

    def _save(self, data):
        self.registry_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _resolve(self, ref):
        path = Path(str(ref)).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(self.root):
            raise ValueError("media_ref must resolve inside the OTH workspace")
        return path

    @staticmethod
    def _hash(path):
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def execute(self, action: str, payload: dict) -> FallbackResult:
        source = payload.get("input", {})
        if action == "list":
            return FallbackResult(True, {"fallback": True, "assets": self._load()["assets"]})
        if action not in {"inspect", "register", "normalize"}:
            return self._unsupported("media-assets", action)
        try:
            path = self._resolve(source.get("media_ref", ""))
        except Exception as exc:
            return FallbackResult(False, {"fallback": True}, str(exc))
        digest = self._hash(path)
        metadata = {
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "suffix": path.suffix.lower(),
        }
        if action == "inspect":
            return FallbackResult(True, {
                "fallback": True,
                "path": str(path),
                "sha256": digest,
                "metadata": metadata,
                "inspection_mode": "filesystem",
            })
        data = self._load()
        existing = next((x for x in data["assets"] if x.get("sha256") == digest), None)
        if existing is None:
            existing = {
                "media_id": f"fallback-media-{len(data['assets']) + 1}",
                "source_path": str(path.relative_to(self.root)),
                "sha256": digest,
                "metadata": metadata,
                "status": "ready",
                "fallback": True,
            }
            data["assets"].append(existing)
        if action == "register":
            self._save(data)
            return FallbackResult(True, {"fallback": True, "asset": existing})
        if path.suffix.lower() == ".mp4":
            existing["normalized_path"] = str(path.relative_to(self.root))
            existing["status"] = "ready"
            existing["normalization_mode"] = "already_compatible"
            self._save(data)
            return FallbackResult(True, {"fallback": True, "asset": existing})
        self._save(data)
        return FallbackResult(True, {
            "fallback": True,
            "asset": existing,
            "status": "needs_primary_normalizer",
            "normalization_mode": "plan_only",
            "reason": "Non-MP4 media requires the primary media toolchain for safe transcoding.",
        })


class MediaIngestFallback(_BaseFallback):
    id = "media-ingest-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.registry = self.root / "data" / "media_sources_fallback.json"
        self.registry.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "media-ingest"

    def _load(self):
        if not self.registry.exists():
            return {"sources": []}
        try:
            return json.loads(self.registry.read_text(encoding="utf-8"))
        except Exception:
            return {"sources": []}

    def _save(self, data):
        self.registry.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def execute(self, action: str, payload: dict) -> FallbackResult:
        source = payload.get("input", {})
        if action == "list":
            return FallbackResult(True, {"fallback": True, "sources": self._load()["sources"]})
        if action != "download":
            return self._unsupported("media-ingest", action)
        url = str(source.get("url", "")).strip()
        if not url:
            return FallbackResult(False, {"fallback": True}, "url is required")
        rows = self._load()
        existing = next((x for x in rows["sources"] if x.get("url") == url), None)
        if existing:
            return FallbackResult(True, {"fallback": True, "sources": [existing], "count": 1})
        row = {
            "source_id": f"fallback-source-{len(rows['sources']) + 1}",
            "url": url,
            "title": source.get("title"),
            "uploader": source.get("uploader"),
            "duration": source.get("duration"),
            "status": "awaiting_download_backend",
            "network": False,
            "fallback": True,
        }
        rows["sources"].append(row)
        self._save(rows)
        return FallbackResult(True, {
            "fallback": True,
            "sources": [row],
            "count": 1,
            "status": "awaiting_download_backend",
            "next": [],
        })


class MediaProductionFallback(_BaseFallback):
    id = "media-production-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "media-production"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action not in {"plan", "list", "review"}:
            return self._unsupported("media-production", action)
        source = payload.get("input", {})
        if action in {"list", "review"}:
            return FallbackResult(True, {"fallback": True, "manifests": []})
        briefs = source.get("briefs") or []
        if isinstance(briefs, dict):
            briefs = [briefs]
        manifests = []
        for brief in briefs[:20]:
            platform = str(brief.get("platform", "social")).lower()
            duration = max(int(brief.get("duration_seconds") or 30), 5)
            aspect = "9:16" if platform in {"instagram", "youtube", "linkedin"} else "1:1"
            manifests.append({
                "manifest_id": f"fallback-prod-{len(manifests) + 1}",
                "brief_id": brief.get("brief_id"),
                "campaign_id": brief.get("campaign_id"),
                "platform": platform,
                "format": brief.get("format"),
                "template": {
                    "aspect_ratio": aspect,
                    "duration_seconds": duration,
                    "captions": "sentence_timed",
                },
                "timeline": [
                    {"id": "hook", "start": 0, "end": min(2, duration), "purpose": "hook"},
                    {"id": "proof", "start": min(2, duration), "end": max(duration - 3, 2), "purpose": "proof"},
                    {"id": "cta", "start": max(duration - 3, 0), "end": duration, "purpose": "cta"},
                ],
                "render": {
                    "resolution": "1080x1920" if aspect == "9:16" else "1080x1080",
                    "frame_rate": 30,
                    "codec": "h264",
                    "container": "mp4",
                },
                "status": "ready_for_primary_renderer",
                "fallback": True,
            })
        return FallbackResult(True, {
            "fallback": True,
            "manifests": manifests,
            "count": len(manifests),
            "next": [],
        })


class SocialQueueFallback(_BaseFallback):
    id = "social-queue-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_queue_fallback.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-queue"

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
        data = self._load()
        content_id = str(source.get("content_id", "")).strip()

        if action == "list":
            return FallbackResult(True, {"fallback": True, "items": data["items"]})
        if action in {"approve", "schedule", "attach_media"}:
            row = next((x for x in data["items"] if x.get("content_id") == content_id), None)
            if row is None:
                return FallbackResult(False, {"fallback": True}, "content_id not found")
            if action == "approve":
                row.setdefault("approval", {})["status"] = "approved"
            elif action == "schedule":
                row["due_at"] = source.get("due_at")
            else:
                row.setdefault("payload", {})["media_ref"] = source.get("media_ref")
                row.setdefault("approval", {})["status"] = "pending"
            self._save(data)
            return FallbackResult(True, {"fallback": True, "item": row})

        if action != "reconcile":
            return self._unsupported("social-queue", action)

        held, dispatches, scheduled = [], [], 0
        now = datetime.now(timezone.utc)
        for row in data["items"]:
            approval = row.get("approval", {}).get("status", "pending")
            due_at = row.get("due_at")
            if approval != "approved":
                held.append({"content_id": row.get("content_id"), "reason": "awaiting_approval"})
                continue
            if due_at:
                try:
                    if datetime.fromisoformat(str(due_at)) > now:
                        scheduled += 1
                        continue
                except ValueError:
                    pass
            platform = str(row.get("platform", "")).lower()
            dispatches.append({
                "capability": "social-actions",
                "action": "publish_video" if platform == "youtube" else "publish_text",
                "priority": 70,
                "payload": {
                    "approved": True,
                    "input": {
                        "content_id": row.get("content_id"),
                        "provider": platform,
                        **row.get("payload", {}),
                    },
                },
                "fallback": True,
            })
        return FallbackResult(True, {
            "fallback": True,
            "held": held,
            "dispatches": dispatches,
            "scheduled": scheduled,
            "external_actions": False,
            "note": "Fallback reconcile emits approval-preserving dispatch plans; it never publishes.",
        })


class SocialActionsFallback(_BaseFallback):
    id = "social-actions-fallback"

    def supports(self, capability: str) -> bool:
        return capability == "social-actions"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action == "doctor":
            providers = []
            for provider in ("linkedin", "youtube", "x", "instagram"):
                providers.append({
                    "provider": provider,
                    "status": "fallback_offline",
                    "live": False,
                    "network_called": False,
                })
            return FallbackResult(True, {
                "fallback": True,
                "providers": providers,
                "live_actions_available": False,
            })
        if action == "prepare_publish":
            source = payload.get("input", {})
            return FallbackResult(True, {
                "fallback": True,
                "status": "approval_required",
                "live_action_available": False,
                "provider": source.get("provider"),
                "content_id": source.get("content_id"),
                "reason": "Independent fallback will not perform external publication.",
            })
        if action in {"publish_text", "publish_video"}:
            return FallbackResult(True, {
                "fallback": True,
                "status": "external_action_unavailable",
                "live": False,
                "approval_required": True,
                "executed": False,
                "reason": "No provider call performed by fallback.",
                "input": payload.get("input", {}),
            })
        return self._unsupported("social-actions", action)

class SocialAccountsFallback(_BaseFallback):
    id = "social-accounts-fallback"
    PROVIDERS = ("linkedin", "youtube", "x", "instagram")

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_accounts_fallback.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-accounts"

    def _load(self):
        if not self.path.exists():
            return {"accounts": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"accounts": []}

    def _save(self, data):
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def execute(self, action: str, payload: dict) -> FallbackResult:
        source = payload.get("input", {})
        provider = str(source.get("provider", "")).lower()
        if action == "status":
            return FallbackResult(True, {
                "fallback": True,
                "accounts": self._load()["accounts"],
                "live_oauth": False,
            })
        if action in {"onboard", "setup"}:
            providers = [provider] if provider in self.PROVIDERS else list(self.PROVIDERS)
            checklist = []
            for item in providers:
                checklist.append({
                    "provider": item,
                    "configured": False,
                    "credential_required": True,
                    "live_oauth": False,
                    "next_step": "configure_official_app_credentials",
                })
            return FallbackResult(True, {
                "fallback": True,
                "checklist": checklist,
                "status": "manual_configuration_required",
            })
        if action == "oauth_start":
            if provider not in self.PROVIDERS:
                return FallbackResult(False, {"fallback": True}, "Unsupported provider")
            return FallbackResult(True, {
                "fallback": True,
                "provider": provider,
                "status": "manual_oauth_required",
                "authorization_url": None,
                "reason": "Fallback does not initiate external OAuth flows.",
            })
        if action == "oauth_callback":
            return FallbackResult(False, {
                "fallback": True,
                "provider": provider,
                "status": "not_supported",
            }, "Fallback will not exchange OAuth codes without the primary account adapter.")
        return self._unsupported("social-accounts", action)


class SocialAutonomyFallback(_BaseFallback):
    id = "social-autonomy-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_autonomy_fallback.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-autonomy"

    def _load(self):
        if not self.path.exists():
            return {"cycles": [], "instructions": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"cycles": [], "instructions": []}

    def _save(self, data):
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def execute(self, action: str, payload: dict) -> FallbackResult:
        source = payload.get("input", {})
        data = self._load()
        if action == "status":
            return FallbackResult(True, {
                "fallback": True,
                "enabled": True,
                "mode": "observe-plan",
                "state": data,
                "external_actions": False,
            })
        if action == "command":
            instruction = str(source.get("instruction", "")).strip()
            if not instruction:
                return FallbackResult(False, {"fallback": True}, "instruction is required")
            data["instructions"].append({
                "instruction": instruction,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            data["instructions"] = data["instructions"][-50:]
            self._save(data)
            return FallbackResult(True, {
                "fallback": True,
                "instruction_recorded": True,
                "next": [{"capability": "social-autonomy", "action": "tick", "priority": 88}],
            })
        if action == "tick":
            queue = source.get("queue") or []
            decisions = []
            pending = sum(
                1 for x in queue
                if x.get("approval", {}).get("status", "pending") == "pending"
            )
            if pending:
                decisions.append({
                    "type": "human_review",
                    "reason": "approval_backlog",
                    "count": pending,
                })
            decisions.append({
                "type": "observe_and_learn",
                "reason": "provider_independent_fallback_cycle",
            })
            cycle = {"at": datetime.now(timezone.utc).isoformat(), "decisions": decisions}
            data["cycles"].append(cycle)
            data["cycles"] = data["cycles"][-50:]
            self._save(data)
            return FallbackResult(True, {
                "fallback": True,
                "decisions": decisions,
                "initiatives": [],
                "external_actions": False,
            })
        return self._unsupported("social-autonomy", action)


class SocialAutopilotFallback(_BaseFallback):
    id = "social-autopilot-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "social-autopilot"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        source = payload.get("input", {})
        if action == "status":
            path = self.root / "data" / "social_autopilot.json"
            state = {}
            if path.exists():
                try:
                    state = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    state = {}
            return FallbackResult(True, {
                "fallback": True,
                "campaigns": state.get("campaigns", []),
                "runs": state.get("runs", [])[-10:],
                "external_actions": False,
            })
        if action != "run":
            return self._unsupported("social-autopilot", action)
        candidates = source.get("candidates") or []
        min_score = float(source.get("min_score", 65))
        max_new = max(0, int(source.get("max_new_campaigns", 1)))
        created = []
        for row in candidates:
            if len(created) >= max_new:
                break
            score = float(row.get("score", 0) or 0)
            if score < min_score:
                continue
            title = str(row.get("title") or row.get("query") or "Opportunity")
            created.append({
                "campaign_id": f"fallback-campaign-{len(created)+1}",
                "market": title,
                "offer": row.get("offer") or f"Solution for {title}",
                "pain": row.get("pain") or row.get("snippet") or "",
                "proof": row.get("proof") or "",
                "score": score,
                "status": "queued_for_review",
                "platforms": source.get("platforms") or ["linkedin", "x", "youtube", "instagram"],
                "fallback": True,
            })
        return FallbackResult(True, {
            "fallback": True,
            "created_campaigns": created,
            "skipped": max(len(candidates) - len(created), 0),
            "external_actions": False,
            "next": [{
                "capability": "social-content",
                "action": "draft",
                "priority": 70,
            }] if created else [],
        })


class SocialControlFallback(_BaseFallback):
    id = "social-control-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "social-control"

    def _read(self, name, default):
        path = self.root / "data" / name
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action not in {"status", "attention"}:
            return self._unsupported("social-control", action)
        queue = self._read("social_queue.json", {"items": []}).get("items", [])
        campaigns = self._read("social_autopilot.json", {"campaigns": []}).get("campaigns", [])
        leads = self._read("social_leads.json", {"leads": []}).get("leads", [])
        attention = []
        pending = [x for x in queue if x.get("approval", {}).get("status") == "pending"]
        failed = [x for x in queue if x.get("status") == "failed"]
        if pending:
            attention.append({"priority": "human_review", "reason": "content_waiting_for_approval", "count": len(pending)})
        if failed:
            attention.append({"priority": "recovery", "reason": "published_action_failed", "count": len(failed)})
        snapshot = {
            "fallback": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "campaigns": len(campaigns),
            "content_items": len(queue),
            "leads": len(leads),
            "pending_approval": len(pending),
            "failed_items": len(failed),
            "attention": attention,
        }
        return FallbackResult(True, snapshot)


class SocialLeadsFallback(_BaseFallback):
    id = "social-leads-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_leads_fallback.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-leads"

    def _load(self):
        if not self.path.exists():
            return {"leads": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"leads": []}

    def _save(self, data):
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _intent(message):
        text = str(message or "").lower()
        buyer = [x for x in ("price", "pricing", "cost", "demo", "buy", "purchase", "interested", "trial", "book") if x in text]
        support = [x for x in ("bug", "error", "broken", "refund", "support") if x in text]
        if buyer:
            return "buyer_intent", min(100, 65 + len(buyer) * 8), buyer
        if support:
            return "support", 35, support
        return "unclear", 20, []

    def execute(self, action: str, payload: dict) -> FallbackResult:
        source = payload.get("input", {})
        data = self._load()
        if action == "ingest":
            message = str(source.get("message", ""))
            intent, score, signals = self._intent(message)
            contact = str(source.get("contact", "")).strip()
            existing = next((x for x in data["leads"] if contact and x.get("contact") == contact), None)
            if existing:
                existing["score"] = max(existing.get("score", 0), score)
                existing["intent"] = intent
                existing["signals"] = sorted(set(existing.get("signals", []) + signals))
                existing["updated_at"] = datetime.now(timezone.utc).isoformat()
                lead = existing
                created = False
            else:
                lead = {
                    "id": f"fallback-lead-{len(data['leads']) + 1}",
                    "platform": source.get("platform", "unknown"),
                    "external_id": source.get("external_id", ""),
                    "contact": contact,
                    "message": message,
                    "intent": intent,
                    "score": score,
                    "signals": signals,
                    "consent": bool(source.get("consent", False)),
                    "status": "new",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                data["leads"].append(lead)
                created = True
            self._save(data)
            return FallbackResult(True, {
                "fallback": True,
                "lead": lead,
                "created": created,
                "followup_allowed": bool(lead.get("consent")),
            })
        if action == "list":
            return FallbackResult(True, {"fallback": True, "leads": data["leads"]})
        if action in {"qualify", "convert"}:
            lead = next((x for x in data["leads"] if x.get("id") == source.get("lead_id")), None)
            if not lead:
                return FallbackResult(False, {"fallback": True}, "Unknown lead")
            lead["status"] = "qualified" if action == "qualify" else "converted"
            self._save(data)
            return FallbackResult(True, {"fallback": True, "lead": lead})
        if action == "summary":
            rows = {}
            for lead in data["leads"]:
                key = lead.get("content_id") or "unattributed"
                row = rows.setdefault(key, {"content_id": key, "leads": 0, "qualified_leads": 0, "conversions": 0})
                row["leads"] += 1
                if lead.get("status") in {"qualified", "converted"}:
                    row["qualified_leads"] += 1
                if lead.get("status") == "converted":
                    row["conversions"] += 1
            return FallbackResult(True, {
                "fallback": True,
                "content_summary": list(rows.values()),
                "next": [{"capability": "social-optimization", "action": "ingest_funnel", "priority": 60}],
            })
        if action == "followup_draft":
            lead = next((x for x in data["leads"] if x.get("id") == source.get("lead_id")), None)
            if not lead:
                return FallbackResult(False, {"fallback": True}, "Unknown lead")
            if not lead.get("consent"):
                return FallbackResult(False, {"fallback": True}, "Follow-up blocked because consent is not recorded")
            return FallbackResult(True, {
                "fallback": True,
                "lead_id": lead["id"],
                "draft": "Thanks for reaching out. Want to share how you handle this today so we can see whether the offer fits?",
                "approval": "required_before_external_send",
            })
        return self._unsupported("social-leads", action)


class SocialMarketFallback(_BaseFallback):
    id = "social-market-fallback"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def supports(self, capability: str) -> bool:
        return capability == "social-market"

    def execute(self, action: str, payload: dict) -> FallbackResult:
        if action not in {"plan", "design"}:
            return self._unsupported("social-market", action)
        source = payload.get("input", {})
        market = str(source.get("market", "target market"))
        offer = str(source.get("offer", "product or service"))
        platforms = source.get("platforms") or ["linkedin", "x", "youtube", "instagram"]
        workflows = [
            {"id": "research", "goal": "Find recurring buyer pain and language.", "steps": ["collect signals", "cluster pain", "score intent"]},
            {"id": "content", "goal": "Turn validated pain into platform-native content.", "steps": ["select pain", "draft content", "review claims", "queue for approval"]},
            {"id": "lead-funnel", "goal": "Capture and qualify opted-in inbound interest.", "steps": ["detect intent", "capture consent", "deduplicate", "score lead"]},
            {"id": "learning", "goal": "Improve the next cycle using outcomes.", "steps": ["measure engagement", "attribute leads", "compare experiments"]},
        ]
        return FallbackResult(True, {
            "fallback": True,
            "market": market,
            "offer": offer,
            "platforms": platforms,
            "strategy": "inbound_first",
            "workflows": workflows,
            "human_approval": ["external", "financial", "irreversible", "public_claim_with_material_business_impact"],
            "next": [{"capability": "automation-build", "action": "build", "priority": 55}],
        })
