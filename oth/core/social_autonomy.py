import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from oth.core.db import Database


@dataclass
class SocialAutonomyResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False


class SocialAutonomy:
    id = "social-autonomy"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.config_path = self.root / "config" / "autonomy.json"
        self.state_path = self.root / "data" / "social_autonomy.json"
        self.pilot_path = self.root / "data" / "pilot_state.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-autonomy"

    def _read(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _save(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _config(self) -> dict[str, Any]:
        return self._read(self.config_path, {
            "enabled": True, "mode": "autonomous-ops",
            "initiative": {"max_new_campaigns_per_tick": 1}
        })

    def _state(self) -> dict[str, Any]:
        return self._read(self.state_path, {
            "cycles": [], "decisions": [], "last_tick_at": None,
            "operating_mode": "autonomous-ops"
        })

    def _pilot(self) -> dict[str, Any]:
        return self._read(self.pilot_path, {
            "goal": "Grow qualified inbound demand through useful content and measurable offers.",
            "constraints": [], "preferences": [], "instructions": [],
            "updated_at": None
        })
    def _interpret_command(self, instruction: str) -> dict[str, Any]:
        text = instruction.strip()
        result = {
            "raw": text, "goal": text, "constraints": [],
            "preferences": [], "tactics_to_try": []
        }
        binary = re.findall(r"(?:don't|do not|avoid|never)\s+([^.;]+)", text, re.I)
        result["constraints"].extend(x.strip() for x in binary)
        prefs = re.findall(
            r"(?:prefer|prioritize|focus on)\s+([^.;]+)", text, re.I
        )
        result["preferences"].extend(x.strip() for x in prefs)
        lowered = text.lower()
        if "reel" in lowered or "short" in lowered:
            result["tactics_to_try"].append("short_form_video")
        if "linkedin" in lowered:
            result["tactics_to_try"].append("linkedin_native")
        if "instagram" in lowered:
            result["tactics_to_try"].append("instagram_reels")
        if "youtube" in lowered:
            result["tactics_to_try"].append("youtube_shorts")
        return result

    def _deep_interpret(self, instruction: str) -> dict[str, Any]:
        hermes = shutil.which("hermes")
        if not hermes:
            return self._interpret_command(instruction)
        prompt = (
            "Return JSON only. You are the strategy interpreter for an autonomous "
            "social operating system. Convert the Pilot instruction into a compact "
            "operating delta. Keys: goal, constraints[], preferences[], "
            "tactics_to_try[]. Do not invent facts. Preserve the user's intent.\n\n"
            f"PILOT INSTRUCTION:\n{instruction}"
        )
        try:
            proc = subprocess.run(
                [hermes, "-z", prompt],
                capture_output=True, text=True, timeout=60, check=False
            )
            if proc.returncode == 0:
                raw = proc.stdout.strip()
                match = re.search(r"\{.*\}", raw, re.S)
                if match:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        return {
                            "raw": instruction,
                            "goal": str(parsed.get("goal") or instruction),
                            "constraints": [str(x) for x in parsed.get("constraints", [])],
                            "preferences": [str(x) for x in parsed.get("preferences", [])],
                            "tactics_to_try": [str(x) for x in parsed.get("tactics_to_try", [])],
                        }
        except Exception:
            pass
        return self._interpret_command(instruction)

    def _apply_command(self, instruction: str) -> dict[str, Any]:
        pilot = self._pilot()
        delta = self._deep_interpret(instruction)
        if delta.get("goal"):
            pilot["goal"] = delta["goal"]
        pilot["constraints"] = list(dict.fromkeys(
            pilot.get("constraints", []) + delta.get("constraints", [])
        ))[-30:]
        pilot["preferences"] = list(dict.fromkeys(
            pilot.get("preferences", []) + delta.get("preferences", [])
        ))[-30:]
        pilot["instructions"] = (pilot.get("instructions", []) + [delta])[-50:]
        pilot["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(self.pilot_path, pilot)
        return delta

    def _snapshot(self) -> dict[str, Any]:
        queue = self._read(self.root / "data" / "social_queue.json", {"items": []})
        accounts = self._read(self.root / "data" / "social_accounts.json", {"accounts": []})
        campaigns = self._read(self.root / "data" / "social_autopilot.json", {"campaigns": []})
        learning = self._read(self.root / "data" / "social_learning.json", {"experiments": []})
        editorial = self._read(self.root / "data" / "social_editorial.json", {"briefs": []})
        production = self._read(self.root / "data" / "production_manifests.json", {"manifests": []})
        resolve = self._read(self.root / "data" / "resolve_state.json", {})
        return {
            "queue": queue.get("items", []),
            "accounts": accounts.get("accounts", []),
            "campaigns": campaigns.get("campaigns", []),
            "experiments": learning.get("experiments", []),
            "editorial_briefs": editorial.get("briefs", []),
            "production_manifests": production.get("manifests", []),
            "resolve": resolve,
        }
    def _due_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        out = []
        for item in items:
            due = item.get("due_at")
            if not due:
                continue
            try:
                if datetime.fromisoformat(str(due)) <= now:
                    out.append(item)
            except ValueError:
                continue
        return out

    def _coverage_hours(self, items: list[dict[str, Any]]) -> float:
        future = []
        for item in items:
            due = item.get("due_at")
            if not due or item.get("status") != "queued":
                continue
            try:
                future.append(datetime.fromisoformat(str(due)))
            except ValueError:
                continue
        if not future:
            return 0.0
        latest = max(future)
        return max((latest - datetime.now(timezone.utc)).total_seconds() / 3600, 0.0)

    def _campaign_payload(self, campaigns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        recent = campaigns[-6:]
        result = []
        for campaign in recent:
            result.append({
                "campaign_id": campaign.get("campaign_id"),
                "market": campaign.get("market"),
                "score": campaign.get("score"),
                "pain": campaign.get("pain"),
                "proof": campaign.get("proof"),
                "hook": campaign.get("learning_reference", {}).get("hook", ""),
                "platforms": campaign.get("platforms", []),
            })
        return result
    def _decide(self, snap: dict[str, Any], config: dict[str, Any],
                pilot: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        initiatives = []
        decisions = []
        queue = snap["queue"]
        campaigns = snap["campaigns"]
        coverage = self._coverage_hours(queue)
        pending_approval = sum(
            1 for x in queue if x.get("approval", {}).get("status") == "pending"
        )
        external_waits = sum(
            1 for x in queue if x.get("status") in {
                "waiting_credentials", "waiting_media", "waiting_capability"
            }
        )
        min_score = float(config.get("decision_rules", {}).get("min_opportunity_score", 65))
        max_campaigns = int(config.get("initiative", {}).get("max_new_campaigns_per_tick", 1))

        if coverage < float(config.get("decision_rules", {}).get("min_content_coverage_hours", 36)):
            initiatives.append({
                "capability": "social-autopilot", "action": "run", "priority": 74,
                "payload": {
                    "input": {
                        "min_score": min_score,
                        "max_new_campaigns": max_campaigns,
                        "platforms": ["linkedin", "x", "youtube", "instagram"],
                    }
                }
            })
            decisions.append({"type": "create_demand", "reason": "low_content_coverage"})
        if campaigns and len(snap["editorial_briefs"]) < len(campaigns) * 4:
            initiatives.append({
                "capability": "social-editor", "action": "plan", "priority": 70,
                "payload": {
                    "input": {
                        "campaigns": self._campaign_payload(campaigns),
                        "platforms": ["linkedin", "x", "youtube", "instagram"],
                        "purpose": "discovery",
                        "funnel_stage": "awareness",
                        "sources": ["OTH opportunity evidence", "campaign proof"],
                    }
                }
            })
            decisions.append({"type": "editorial_gap", "reason": "creative_briefs_missing"})
        if snap["editorial_briefs"] and len(snap["production_manifests"]) < len(snap["editorial_briefs"]):
            initiatives.append({
                "capability": "media-production", "action": "plan", "priority": 72,
                "payload": {"input": {"briefs": snap["editorial_briefs"][-12:]}}
            })
            decisions.append({"type": "production_gap", "reason": "production_manifests_missing"})
        if snap["production_manifests"]:
            if not snap["resolve"].get("installed", False):
                decisions.append({"type": "production_dependency", "reason": "resolve_not_installed"})
            elif snap["resolve"].get("activation_required", False):
                decisions.append({"type": "production_dependency", "reason": "resolve_activation_required"})
        if any(x.get("status") == "failed" for x in queue):
            if config.get("decision_rules", {}).get("replan_after_failed_publish", True):
                initiatives.append({
                    "capability": "social-editor", "action": "review", "priority": 69,
                    "payload": {"input": {}}
                })
                decisions.append({"type": "replan", "reason": "publish_failure_detected"})
        initiatives.append({
            "capability": "social-analytics", "action": "sync", "priority": 62,
            "payload": {"input": {}}
        })
        initiatives.append({
            "capability": "social-optimizer", "action": "optimize", "priority": 61,
            "payload": {"input": {}}
        })
        decisions.append({
            "type": "observe_and_learn",
            "pending_approval": pending_approval,
            "external_waits": external_waits,
            "pilot_goal": pilot.get("goal"),
        })
        return initiatives, decisions
    def execute(self, action: str, payload: dict) -> SocialAutonomyResult:
        if action not in {"tick", "status", "command"}:
            return SocialAutonomyResult(False, {}, f"Unsupported social-autonomy action: {action}")
        config = self._config()
        state = self._state()
        pilot = self._pilot()

        if action == "status":
            snap = self._snapshot()
            return SocialAutonomyResult(True, {
                "enabled": bool(config.get("enabled", True)),
                "mode": config.get("mode", "autonomous-ops"),
                "pilot": pilot,
                "state": state,
                "snapshot": {
                    "accounts": len(snap["accounts"]),
                    "campaigns": len(snap["campaigns"]),
                    "queue_items": len(snap["queue"]),
                    "editorial_briefs": len(snap["editorial_briefs"]),
                    "production_manifests": len(snap["production_manifests"]),
                    "resolve_installed": bool(snap["resolve"].get("installed", False)),
                    "experiments": len(snap["experiments"]),
                },
                "publish_mode": config.get("initiative", {}).get("publish_mode", "approval"),
            })

        source = payload.get("input", {})
        if action == "command":
            instruction = str(source.get("instruction", "")).strip()
            if not instruction:
                return SocialAutonomyResult(False, {}, "instruction is required")
            delta = self._apply_command(instruction)
            return SocialAutonomyResult(True, {
                "pilot_delta": delta,
                "pilot": self._pilot(),
                "next": [{
                    "capability": "social-autonomy",
                    "action": "tick",
                    "priority": 90,
                }],
            })

        if not config.get("enabled", True):
            return SocialAutonomyResult(True, {"status": "disabled"})
        snap = self._snapshot()
        initiatives, decisions = self._decide(snap, config, pilot)
        state["last_tick_at"] = datetime.now(timezone.utc).isoformat()
        state["operating_mode"] = config.get("mode", "autonomous-ops")
        state.setdefault("cycles", []).append({
            "at": state["last_tick_at"],
            "decisions": decisions,
            "initiative_count": len(initiatives),
        })
        state["cycles"] = state["cycles"][-50:]
        state.setdefault("decisions", []).extend(decisions)
        state["decisions"] = state["decisions"][-100:]
        self._save(self.state_path, state)
        return SocialAutonomyResult(True, {
            "decisions": decisions,
            "initiatives": initiatives,
            "pilot": pilot,
            "coverage_hours": self._coverage_hours(snap["queue"]),
            "next": initiatives,
        })


__all__ = ["SocialAutonomy", "SocialAutonomyResult"]
