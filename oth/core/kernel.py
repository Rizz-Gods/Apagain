import json
import uuid
from pathlib import Path
from .db import Database
from .models import Task, now_iso
from .mission_state import MissionStateStore
from .policy import PolicyGate
from .registry import Registry
from .workforce import WorkforceRegistry
from .triggers import EventTriggerEngine
from .lanes import LaneRouter
from .evaluator import ExecutionEvaluator
from .analyst import OpportunityAnalyst
from .opportunity_fallback import OpportunityAnalystFallback
from .automation_builder import AutomationBuilder
from .automation_designer import AutomationDesigner
from .automation_design_fallback import AutomationDesignerFallback
from .dependency_provisioner import DependencyProvisioner
from .promotion_gate import PromotionGate
from .workflow_compiler import WorkflowCompiler
from .qa_validator import QAValidator
from .review_miner import ReviewMiner
from .review_miner_fallback import ReviewMinerFallback
from .skills import SkillAcquirer
from .tools import ToolRegistry
from oth.workers.browser import BrowserWorker
from oth.workers.builtin import BuiltinWorker, WorkerResult
from oth.workers.external import ExternalAgentWorker
from oth.core.scout import ScoutWorker
from oth.core.web_scout import WebScoutHTTPWorker
from oth.core.local_reasoner import LocalReasonerWorker
from oth.core.engineering import EngineeringWorker
from oth.core.ollama_engineer import NativeOllamaEngineer
from oth.core.engineering_fallback import EngineeringFallback
from oth.core.engineering_evidence import engineering_result_valid
from oth.core.social_market import SocialMarketWorker
from oth.core.social_accounts import SocialAccountManager
from oth.core.social_content import SocialContentEngine
from oth.core.social_leads import SocialLeadEngine
from oth.core.social_autopilot import SocialAutopilot
from oth.core.social_queue import SocialQueueManager
from oth.core.social_control import SocialControl
from oth.core.social_optimizer import SocialOptimizer
from oth.core.social_actions import SocialActionBus
from oth.core.social_analytics import SocialAnalytics
from oth.core.media_assets import MediaAssetManager
from oth.core.social_planner import SocialPlanner
from oth.core.social_editor import SocialEditorialDirector
from oth.core.social_autonomy import SocialAutonomy
from oth.core.media_producer import MediaProducer
from oth.core.resolve_bridge import ResolveBridge
from oth.core.media_ingest import MediaIngest
from oth.core.media_transcription import MediaTranscription
from oth.core.media_qa import MediaQA
from oth.core.resilient_fallbacks import (
    AutomationBuilderFallback, QAFallback, PromotionFallback,
    DependencyProvisionFallback, WorkflowCompilerFallback,
    MediaQAFallback, MediaTranscriptionFallback,
    SocialAnalyticsFallback, SocialOptimizationFallback, SocialContentFallback,
    SocialPlannerFallback, SocialEditorialFallback,
    MediaAssetsFallback, MediaIngestFallback, MediaProductionFallback,
    SocialQueueFallback, SocialActionsFallback,
    SocialAccountsFallback, SocialAutonomyFallback, SocialAutopilotFallback,
    SocialControlFallback, SocialLeadsFallback, SocialMarketFallback,
    BrowserHTTPFallback, ResolveBridgeFallback,
)

class OTHKernel:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.db = Database(self.root / "data" / "oth.db")
        self.missions = MissionStateStore(self.root / "data" / "console.db")
        self.registry = Registry(
            self.root / "config" / "agents.json",
            self.root / "config" / "skills.json",
        )
        self.workforce = WorkforceRegistry(self.root)
        self.trigger_engine = EventTriggerEngine(self.root)
        self.lanes = LaneRouter(self.root)
        self.evaluator = ExecutionEvaluator()
        self.skill_acquirer = SkillAcquirer(self.root)
        self.policy = PolicyGate(self.root / "config" / "policies.json")
        self.tools = ToolRegistry(self.root / "config" / "tools.json")
        self.workers = [BuiltinWorker()]
        modes = set()
        for agent in self.registry.load_agents():
            mode = agent.metadata.get("mode")
            if mode == "local-reasoning":
                self.workers.append(LocalReasonerWorker())
            elif mode == "engineering-ollama":
                self.workers.append(NativeOllamaEngineer(self.root))
                modes.add("engineering")
            elif mode == "engineering-opencode":
                self.workers.append(EngineeringWorker(self.root))
                modes.add("engineering")
            elif mode == "engineering-fallback":
                self.workers.append(EngineeringFallback(self.root))
                modes.add("engineering")
            elif mode == "browser":
                self.workers.append(BrowserWorker(agent))
            elif mode == "scout":
                self.workers.append(ScoutWorker(agent))
                modes.add("scout")
            elif mode == "scout-http":
                self.workers.append(WebScoutHTTPWorker(agent))
                modes.add("scout-http")
            elif mode == "analysis":
                self.workers.append(OpportunityAnalyst())
                modes.add("analysis")
            elif mode == "analysis-fallback":
                self.workers.append(OpportunityAnalystFallback())
                modes.add("analysis-fallback")
            elif mode == "review-mining":
                self.workers.append(ReviewMiner(agent))
                modes.add("review-mining")
            elif mode == "review-mining-fallback":
                self.workers.append(ReviewMinerFallback())
                modes.add("review-mining-fallback")
            elif mode == "automation-design":
                self.workers.append(AutomationDesigner())
                modes.add("automation-design")
            elif mode == "automation-design-fallback":
                self.workers.append(AutomationDesignerFallback())
                modes.add("automation-design-fallback")
            elif mode == "automation-build":
                self.workers.append(AutomationBuilder(self.root))
                modes.add("automation-build")
                modes.add("automation-build")
            elif mode == "qa":
                self.workers.append(QAValidator(self.root))
                modes.add("qa")
                modes.add("qa")
            elif mode == "promotion":
                self.workers.append(PromotionGate())
                modes.add("promotion")
            elif mode == "provisioning":
                self.workers.append(DependencyProvisioner())
                modes.add("provisioning")
            elif mode == "compiler":
                self.workers.append(WorkflowCompiler(self.root))
                modes.add("compiler")
            elif mode == "social-market":
                self.workers.append(SocialMarketWorker(self.root))
                modes.add("social-market")
            elif mode == "social-accounts":
                self.workers.append(SocialAccountManager(self.root))
                modes.add("social-accounts")
            elif mode == "social-optimization":
                self.workers.append(SocialOptimizer(self.root))
                modes.add("social-optimization")
            elif mode == "social-content":
                self.workers.append(SocialContentEngine(self.root))
                modes.add("social-content")
            elif mode == "social-leads":
                self.workers.append(SocialLeadEngine(self.root))
                modes.add("social-leads")
            elif mode == "social-autopilot":
                self.workers.append(SocialAutopilot(self.root))
                modes.add("social-autopilot")
            elif mode == "social-queue":
                self.workers.append(SocialQueueManager(self.root))
                modes.add("social-queue")
            elif mode == "social-control":
                self.workers.append(SocialControl(self.root))
                modes.add("social-control")
            elif mode == "social-actions":
                self.workers.append(SocialActionBus(self.root))
                modes.add("social-actions")
            elif mode == "social-analytics":
                self.workers.append(SocialAnalytics(self.root))
                modes.add("social-analytics")
            elif mode == "media-assets":
                self.workers.append(MediaAssetManager(self.root))
                modes.add("media-assets")
            elif mode == "social-planner":
                self.workers.append(SocialPlanner(self.root))
                modes.add("social-planner")
            elif mode == "social-editor":
                self.workers.append(SocialEditorialDirector(self.root))
                modes.add("social-editor")
            elif mode == "social-autonomy":
                self.workers.append(SocialAutonomy(self.root))
                modes.add("social-autonomy")
            elif mode == "media-production":
                self.workers.append(MediaProducer(self.root))
                modes.add("media-production")
            elif mode == "resolve-bridge":
                self.workers.append(ResolveBridge(self.root))
                modes.add("resolve-bridge")
            elif mode == "media-ingest":
                self.workers.append(MediaIngest(self.root))
                modes.add("media-ingest")
            elif mode == "media-transcription":
                self.workers.append(MediaTranscription(self.root))
                modes.add("media-transcription")
            elif mode == "media-qa":
                self.workers.append(MediaQA(self.root))
                modes.add("media-qa")
            elif mode == "automation-build-fallback":
                self.workers.append(AutomationBuilderFallback(self.root))
                modes.add("automation-build-fallback")
            elif mode == "qa-fallback":
                self.workers.append(QAFallback(self.root))
                modes.add("qa-fallback")
            elif mode == "promotion-fallback":
                self.workers.append(PromotionFallback())
                modes.add("promotion-fallback")
            elif mode == "provisioning-fallback":
                self.workers.append(DependencyProvisionFallback())
                modes.add("provisioning-fallback")
            elif mode == "compiler-fallback":
                self.workers.append(WorkflowCompilerFallback(self.root))
                modes.add("compiler-fallback")
            elif mode == "media-qa-fallback":
                self.workers.append(MediaQAFallback(self.root))
                modes.add("media-qa-fallback")
            elif mode == "media-transcription-fallback":
                self.workers.append(MediaTranscriptionFallback(self.root))
                modes.add("media-transcription-fallback")
            elif mode == "social-analytics-fallback":
                self.workers.append(SocialAnalyticsFallback(self.root))
                modes.add("social-analytics-fallback")
            elif mode == "social-optimization-fallback":
                self.workers.append(SocialOptimizationFallback(self.root))
                modes.add("social-optimization-fallback")
            elif mode == "social-content-fallback":
                self.workers.append(SocialContentFallback())
                modes.add("social-content-fallback")
            elif mode == "social-planner-fallback":
                self.workers.append(SocialPlannerFallback())
                modes.add("social-planner-fallback")
            elif mode == "social-editor-fallback":
                self.workers.append(SocialEditorialFallback())
                modes.add("social-editor-fallback")
            elif mode == "media-assets-fallback":
                self.workers.append(MediaAssetsFallback(self.root))
                modes.add("media-assets-fallback")
            elif mode == "media-ingest-fallback":
                self.workers.append(MediaIngestFallback(self.root))
                modes.add("media-ingest-fallback")
            elif mode == "media-production-fallback":
                self.workers.append(MediaProductionFallback())
                modes.add("media-production-fallback")
            elif mode == "social-queue-fallback":
                self.workers.append(SocialQueueFallback(self.root))
                modes.add("social-queue-fallback")
            elif mode == "social-actions-fallback":
                self.workers.append(SocialActionsFallback())
                modes.add("social-actions-fallback")
            elif mode == "social-accounts-fallback":
                self.workers.append(SocialAccountsFallback(self.root))
                modes.add("social-accounts-fallback")
            elif mode == "social-autonomy-fallback":
                self.workers.append(SocialAutonomyFallback(self.root))
                modes.add("social-autonomy-fallback")
            elif mode == "social-autopilot-fallback":
                self.workers.append(SocialAutopilotFallback(self.root))
                modes.add("social-autopilot-fallback")
            elif mode == "social-control-fallback":
                self.workers.append(SocialControlFallback(self.root))
                modes.add("social-control-fallback")
            elif mode == "social-leads-fallback":
                self.workers.append(SocialLeadsFallback(self.root))
                modes.add("social-leads-fallback")
            elif mode == "social-market-fallback":
                self.workers.append(SocialMarketFallback(self.root))
                modes.add("social-market-fallback")
            elif mode == "browser-http-fallback":
                self.workers.append(BrowserHTTPFallback())
                modes.add("browser-http-fallback")
            elif mode == "resolve-bridge-fallback":
                self.workers.append(ResolveBridgeFallback(self.root))
                modes.add("resolve-bridge-fallback")
            else:
                self.workers.append(ExternalAgentWorker(agent))
        if "scout" not in modes:
            self.workers.append(ScoutWorker())
        if "analysis" not in modes:
            self.workers.append(OpportunityAnalyst())
        if "review-mining" not in modes:
            self.workers.append(ReviewMiner())
        if "automation-design" not in modes:
            self.workers.append(AutomationDesigner())
        if "automation-build" not in modes:
            self.workers.append(AutomationBuilder(self.root))
        if "qa" not in modes:
            self.workers.append(QAValidator(self.root))
        if "promotion" not in modes:
            self.workers.append(PromotionGate())
        if "provisioning" not in modes:
            self.workers.append(DependencyProvisioner())
        if "compiler" not in modes:
            self.workers.append(WorkflowCompiler(self.root))
        if "social-market" not in modes:
            self.workers.append(SocialMarketWorker(self.root))
        if "social-accounts" not in modes:
            self.workers.append(SocialAccountManager(self.root))
        if "social-optimization" not in modes:
            self.workers.append(SocialOptimizer(self.root))
        if "social-content" not in modes:
            self.workers.append(SocialContentEngine(self.root))
        if "social-leads" not in modes:
            self.workers.append(SocialLeadEngine(self.root))
        if "social-autopilot" not in modes:
            self.workers.append(SocialAutopilot(self.root))
        if "social-queue" not in modes:
            self.workers.append(SocialQueueManager(self.root))
        if "social-control" not in modes:
            self.workers.append(SocialControl(self.root))
        if "social-actions" not in modes:
            self.workers.append(SocialActionBus(self.root))
        if "social-analytics" not in modes:
            self.workers.append(SocialAnalytics(self.root))
        if "media-assets" not in modes:
            self.workers.append(MediaAssetManager(self.root))
        if "social-planner" not in modes:
            self.workers.append(SocialPlanner(self.root))
        if "social-editor" not in modes:
            self.workers.append(SocialEditorialDirector(self.root))
        if "social-autonomy" not in modes:
            self.workers.append(SocialAutonomy(self.root))
        if "media-production" not in modes:
            self.workers.append(MediaProducer(self.root))
        if "resolve-bridge" not in modes:
            self.workers.append(ResolveBridge(self.root))
        if "media-ingest" not in modes:
            self.workers.append(MediaIngest(self.root))
        if "media-transcription" not in modes:
            self.workers.append(MediaTranscription(self.root))
        if "media-qa" not in modes:
            self.workers.append(MediaQA(self.root))

    def submit(self, capability: str, action: str, payload: dict, priority: int = 50) -> Task:
        task_payload = dict(payload)
        mission_id = str(task_payload.get("mission_id") or "").strip()
        status = "queued"
        budget_block = None
        if mission_id:
            decision = self.missions.can_create_task(mission_id, self.db.path)
            if not decision.get("allowed"):
                status = "blocked"
                budget_block = decision
                task_payload["_budget_blocked"] = True
                task_payload["_budget_reason"] = decision.get("reason")
        task = Task(str(uuid.uuid4()), capability, action, task_payload, priority, status=status)
        self.db.add_task(task)
        if budget_block:
            self.db.add_event(
                task.id,
                "task.budget_exhausted",
                {
                    "mission_id": mission_id,
                    "reason": budget_block.get("reason"),
                    "budget": budget_block,
                },
                task.created_at,
            )
            self.missions.add_timeline_event(
                mission_id,
                "mission.budget_blocked_task",
                {"task_id": task.id, "reason": budget_block.get("reason"), "budget": budget_block},
                task_id=task.id,
                status="blocked",
                created_at=task.created_at,
            )
            self.missions.update_from_task(
                mission_id,
                task.id,
                "blocked",
                {"error": budget_block.get("reason"), "budget": budget_block},
                task_db=self.db.path,
            )
            self.missions.update_budget_status(mission_id, self.db.path)
        else:
            self.db.add_event(task.id, "task.queued",
                              {"capability": capability, "action": action},
                              task.created_at)
        return task

    def dispatch(self, task_id: str):
        rows = [r for r in self.db.list_tasks() if r["id"] == task_id]
        if not rows:
            raise ValueError(f"Unknown task: {task_id}")
        row = rows[0]
        if row["status"] == "cancelled":
            return {
                "status": "cancelled",
                "task_id": task_id,
                "mission_id": json.loads(row["payload"] or "{}").get("mission_id"),
                "reason": "operator_cancelled",
            }
        stored_payload = json.loads(row["payload"])
        task_payload = dict(stored_payload)
        if task_payload.get("prompt"):
            task_payload["skill_context"] = self.skill_acquirer.context_for(task_payload["prompt"])
            memories = self.db.recent_memories(row["capability"], 5)
            task_payload["memory_context"] = "\n".join(
                f'{m["created_at"]}: {m["content"]}' for m in memories
            )
        capability_contract = self.workforce.capability_for(row["capability"])
        risk_order = {"safe": 0, "local_write": 1, "external": 2, "financial": 3}
        current_risk = str(task_payload.get("risk", "safe")).lower()
        if risk_order.get(capability_contract.risk, 0) > risk_order.get(current_risk, 0):
            task_payload["risk"] = capability_contract.risk
        if row["capability"] == "social-actions" and row["action"] in {"publish_text", "publish_video"}:
            task_payload["risk"] = "external"
        mission_id = str(stored_payload.get("mission_id") or "").strip()
        mission_policy = self.missions.policy_for_mission(mission_id) if mission_id else None
        policy_config = None
        policy_revision = None
        policy_hash = None
        if mission_policy:
            policy_config = mission_policy.get("policy", {}).get("approval", {})
            policy_revision = mission_policy.get("revision")
            policy_hash = mission_policy.get("hash")
        decision = self.policy.check(task_payload, config=policy_config)
        self.db.add_event(
            task_id,
            "task.policy_evaluated",
            {
                "decision": "allowed" if decision.allowed else "blocked",
                "reason": decision.reason,
                "risk": task_payload.get("risk", "safe"),
                "policy_revision": policy_revision,
                "policy_hash": policy_hash,
                "mission_id": mission_id or None,
            },
            now_iso(),
        )
        if not decision.allowed:
            now = now_iso()
            self.db.update_task(task_id, "blocked", now)
            self.db.add_event(task_id, "task.approval_required", {"reason": decision.reason}, now)
            self.db.add_event(
                task_id,
                "task.escalation_required",
                {"target": "pilot", "reason": decision.reason},
                now,
            )
            mission_id = str(stored_payload.get("mission_id") or "").strip()
            if mission_id:
                self.missions.update_from_task(
                    mission_id,
                    task_id,
                    "blocked",
                    {"error": decision.reason, "approval_required": True},
                    task_db=self.db.path,
                )
            return {
                "status": "blocked",
                "reason": decision.reason,
                "approval_required": True,
                "mission_id": mission_id or None,
            }

        worker_map = {
            getattr(worker, "id", "builtin"): worker
            for worker in self.workers
        }
        excluded_workers = set(stored_payload.get("_failed_lane_workers", []))
        lane_candidates = self.lanes.candidates(
            self,
            row["capability"],
            row["action"],
            excluded_workers=excluded_workers,
        )
        executable_lanes = [
            candidate for candidate in lane_candidates
            if candidate.worker_id in worker_map
        ]

        if not executable_lanes:
            now = now_iso()
            self.db.update_task(task_id, "blocked", now)
            reason = "no_worker" if not lane_candidates else "worker_runtime_unavailable"
            self.db.add_event(task_id, "task.blocked", {"reason": reason}, now)
            self.db.add_event(
                task_id,
                "task.escalation_required",
                {"target": "pilot", "reason": reason},
                now,
            )
            mission_id = str(stored_payload.get("mission_id") or "").strip()
            if mission_id:
                self.missions.update_from_task(
                    mission_id,
                    task_id,
                    "blocked",
                    {"error": reason, "approval_required": reason != "no_worker"},
                    task_db=self.db.path,
                )
            return {
                "status": "blocked",
                "reason": reason,
                "approval_required": reason != "no_worker",
                "mission_id": mission_id or None,
            }

        self.db.update_task(task_id, "running", now_iso())
        self.db.add_event(
            task_id,
            "task.started",
            {"lanes": [
                {
                    "lane": candidate.lane,
                    "capability": candidate.capability,
                    "action": candidate.action,
                    "worker_id": candidate.worker_id,
                }
                for candidate in executable_lanes
            ]},
            now_iso(),
        )

        lane_history = []
        result = None
        selected_candidate = None
        for index, candidate in enumerate(executable_lanes):
            if index > 0:
                self.db.add_event(
                    task_id,
                    "lane.switched",
                    {
                        "from_lane": executable_lanes[index - 1].lane,
                        "to_lane": candidate.lane,
                        "reason": lane_history[-1].get("error", "previous lane failed"),
                    },
                    now_iso(),
                )

            worker = worker_map[candidate.worker_id]
            lane_payload = dict(task_payload)
            lane_payload["execution_lane"] = candidate.lane
            if candidate.capability != row["capability"] or candidate.action != row["action"]:
                lane_payload["lane_fallback_from"] = {
                    "capability": row["capability"],
                    "action": row["action"],
                }

            self.db.add_event(
                task_id,
                f"lane.{candidate.lane}.started",
                {
                    "capability": candidate.capability,
                    "action": candidate.action,
                    "worker_id": candidate.worker_id,
                },
                now_iso(),
            )
            lane_result = worker.execute(candidate.action, lane_payload)
            if row["capability"] == "engineering" and lane_result.success and not engineering_result_valid(
                candidate.action,
                lane_result.output,
                lane_result.success,
            ):
                lane_result = WorkerResult(
                    False,
                    dict(lane_result.output or {}),
                    "implementation_evidence_missing",
                    retryable=True,
                )
            lane_history.append({
                "lane": candidate.lane,
                "worker_id": candidate.worker_id,
                "capability": candidate.capability,
                "action": candidate.action,
                "success": lane_result.success,
                "error": lane_result.error,
                "retryable": lane_result.retryable,
            })
            self.db.record_agent_result(
                candidate.worker_id,
                lane_result.success,
                lane_result.error,
                now_iso(),
            )

            if lane_result.success:
                self.lanes.record_success(self, task_id, candidate)
                result = lane_result
                selected_candidate = candidate
                break

            self.lanes.record_failure(self, task_id, candidate, lane_result.error)
            stored_payload.setdefault("_failed_lane_workers", [])
            if candidate.worker_id not in stored_payload["_failed_lane_workers"]:
                stored_payload["_failed_lane_workers"].append(candidate.worker_id)

        if result is None:
            result = WorkerResult(
                False,
                {},
                "all execution lanes failed",
                retryable=any(item["retryable"] for item in lane_history),
            )

        status = "succeeded" if result.success else "failed"
        selected_worker_id = (
            selected_candidate.worker_id
            if selected_candidate
            else lane_history[-1]["worker_id"]
        )
        contract = self.workforce.contract_for(selected_worker_id)
        evaluation = self.evaluator.evaluate(
            success=result.success,
            result_output=result.output,
            error=result.error,
            lane_history=lane_history,
        )
        self.db.record_evaluation(
            task_id,
            row["capability"],
            evaluation.worker_id,
            evaluation.quality,
            evaluation.success,
            evaluation.lane,
            evaluation.observations,
            evaluation.lesson,
            now_iso(),
        )
        self.db.add_event(
            task_id,
            "task.evaluated",
            {
                "quality": evaluation.quality,
                "worker_id": evaluation.worker_id,
                "lane": evaluation.lane,
                "lesson": evaluation.lesson,
                "observations": evaluation.observations,
            },
            now_iso(),
        )
        configured_retries = int(
            stored_payload.get("max_retries", contract.retry.max_attempts)
        )
        retry_scheduled = False
        retry_budget_blocked = None

        # A lane failure is a reason to continue into the next recovery cycle,
        # even when an individual worker reported the error as non-retryable.
        if (
            not result.success
            and int(stored_payload.get("_attempts", 0)) < configured_retries
        ):
            mission_id_for_budget = str(stored_payload.get("mission_id") or "").strip()
            if mission_id_for_budget:
                retry_budget = self.missions.can_retry_task(
                    mission_id_for_budget,
                    self.db.path,
                )
                if not retry_budget.get("allowed"):
                    retry_budget_blocked = retry_budget
                else:
                    stored_payload["_attempts"] = int(stored_payload.get("_attempts", 0)) + 1
                    self.db.update_task_payload(task_id, stored_payload, now_iso())
                    self.db.update_task(task_id, "queued", now_iso())
                    self.db.add_event(
                        task_id,
                        "task.retry_scheduled",
                        {
                            "attempt": stored_payload["_attempts"],
                            "reason": "lane_exhausted",
                            "failed_workers": stored_payload.get("_failed_lane_workers", []),
                            "mission_budget": retry_budget,
                        },
                        now_iso(),
                    )
                    retry_scheduled = True
            else:
                stored_payload["_attempts"] = int(stored_payload.get("_attempts", 0)) + 1
                self.db.update_task_payload(task_id, stored_payload, now_iso())
                self.db.update_task(task_id, "queued", now_iso())
                self.db.add_event(
                    task_id,
                    "task.retry_scheduled",
                    {
                        "attempt": stored_payload["_attempts"],
                        "reason": "lane_exhausted",
                        "failed_workers": stored_payload.get("_failed_lane_workers", []),
                    },
                    now_iso(),
                )
                retry_scheduled = True

        if not retry_scheduled:
            self.db.update_task(task_id, status, now_iso())
            if retry_budget_blocked and mission_id_for_budget:
                self.db.add_event(
                    task_id,
                    "task.budget_exhausted",
                    {
                        "reason": retry_budget_blocked.get("reason"),
                        "budget": retry_budget_blocked,
                    },
                    now_iso(),
                )
                self.missions.update_budget_status(mission_id_for_budget, self.db.path)

        lane_output = dict(result.output or {})
        lane_output["execution_lanes"] = lane_history
        lane_output["evaluation"] = {
            "quality": evaluation.quality,
            "lesson": evaluation.lesson,
            "observations": evaluation.observations,
        }
        if result.success and row["capability"] in ("scout", "review-mining"):
            self.db.add_opportunities(result.output.get("signals", []))
        if result.success and row["capability"] == "opportunity-analysis":
            for item in result.output.get("opportunities", []):
                signal = item.get("signal", item)
                score = item.get("score")
                if not isinstance(score, dict):
                    continue
                oid = self.db.get_opportunity_id(
                    signal.get("source", ""), signal.get("url", ""), signal.get("query", "")
                )
                if oid is not None:
                    self.db.score_opportunity(oid, score, now_iso())
        if result.success and row["capability"] == "automation-design":
            for item in result.output.get("blueprints", []):
                signal = item
                blueprint = item.get("blueprint")
                if not isinstance(blueprint, dict):
                    continue
                oid = self.db.get_opportunity_id(
                    signal.get("source", ""), signal.get("url", ""), signal.get("query", "")
                )
                if oid is not None:
                    self.db.add_blueprint(oid, blueprint, now_iso())
        if result.success and row["capability"] == "automation-build":
            for item in result.output.get("projects", []):
                opp = item.get("opportunity") or {}
                oid = self.db.get_opportunity_id(
                    opp.get("source", ""), opp.get("url", ""), opp.get("query", "")
                )
                if oid is not None:
                    self.db.add_build_artifact(
                        oid,
                        item.get("project_path", ""),
                        item.get("manifest", {}),
                        "generated",
                        now_iso(),
                    )
        if result.success and row["capability"] == "qa-validation":
            for item in result.output.get("results", []):
                project_path = item.get("project_path", "")
                opp = item.get("opportunity", {}) or {}
                oid = self.db.get_opportunity_id(
                    opp.get("source", ""), opp.get("url", ""), opp.get("query", "")
                ) or 0
                self.db.add_qa_result(
                    oid,
                    project_path,
                    item.get("status", "failed"),
                    item.get("checks", []),
                    item.get("warnings", []),
                    item.get("errors", []),
                    now_iso(),
                )
        if result.success and row["capability"] == "promotion-gate":
            for decision in result.output.get("decisions", []):
                project_path = decision.get("project_path", "")
                opp = decision.get("opportunity", {}) or {}
                oid = self.db.get_opportunity_id(
                    opp.get("source", ""), opp.get("url", ""), opp.get("query", "")
                ) or 0
                self.db.add_promotion_result(
                    oid,
                    project_path,
                    decision.get("status", "held"),
                    decision.get("reason", ""),
                    now_iso(),
                )
                self.db.update_build_status(project_path, decision.get("status", "held"))
        effective_status = "retry_queued" if retry_scheduled else status
        self.db.add_memory(
            "task_result",
            row["capability"],
            {
                "task_id": task_id,
                "action": row["action"],
                "status": effective_status,
                "error": result.error,
                "output": lane_output,
                "retryable": result.retryable,
            },
            now_iso(),
        )
        self.db.add_event(
            task_id,
            f"task.{effective_status}",
            {
                "output": lane_output,
                "error": result.error,
                "retryable": result.retryable,
                "execution_lanes": lane_history,
            },
            now_iso(),
        )
        mission_id = str(stored_payload.get("mission_id") or "").strip()
        spawned = []
        if result.success:
            handoffs = task_payload.get("next") or result.output.get("next") or []
            for spec in handoffs:
                child_payload = dict(spec.get("payload", {}))
                handoff_source = child_payload.pop("input_from", None)
                if handoff_source == "event.output":
                    child_payload["input"] = result.output
                elif handoff_source == "event.task":
                    child_payload["input"] = {
                        "task_id": task_id,
                        "capability": row["capability"],
                        "action": row["action"],
                        "status": effective_status,
                    }
                elif "input" not in child_payload:
                    child_payload["input"] = result.output
                for continuity_key in ("mission_id", "conversation_id"):
                    if task_payload.get(continuity_key) and not child_payload.get(continuity_key):
                        child_payload[continuity_key] = task_payload[continuity_key]
                child = self.submit(
                    spec["capability"],
                    spec["action"],
                    child_payload,
                    int(spec.get("priority", 50)),
                )
                spawned.append(child.id)
                self.db.add_task_edge(
                    task_id,
                    child.id,
                    str(spec.get("edge_type", "handoff")),
                    now_iso(),
                )
                self.db.add_event(
                    task_id, "task.spawned",
                    {
                        "child_task_id": child.id,
                        "capability": child.capability,
                        "edge_type": str(spec.get("edge_type", "handoff")),
                    },
                    now_iso(),
                )
        trigger_task = {
            "id": task_id,
            "capability": row["capability"],
            "action": row["action"],
            "status": effective_status,
            "mission_id": task_payload.get("mission_id"),
            "conversation_id": task_payload.get("conversation_id"),
        }
        spawned.extend(
            self.trigger_engine.fire(self, f"task.{effective_status}", trigger_task, result.output)
        )
        if mission_id:
            verification = lane_output.get("verification")
            verification_passed = None
            if isinstance(verification, dict):
                if "passed" in verification:
                    verification_passed = bool(verification["passed"])
                elif "returncode" in verification:
                    verification_passed = int(verification["returncode"]) == 0
            self.missions.update_from_task(
                mission_id,
                task_id,
                effective_status,
                {
                    "summary": lane_output.get("summary"),
                    "provider": lane_output.get("provider"),
                    "model": lane_output.get("model"),
                    "error": result.error,
                    "quality": evaluation.quality,
                    "implementation_changed": lane_output.get("implementation_changed"),
                    "verification_passed": verification_passed,
                    "spawned_tasks": spawned,
                },
                task_db=self.db.path,
            )
        return {"status": effective_status, **lane_output,
                "error": result.error, "spawned": spawned,
                "retryable": result.retryable}

    def resume_mission(
        self,
        mission_id: str,
        task_ids: list[str] | None = None,
        approve_external: bool = False,
    ) -> dict:
        mission = self.missions.get(mission_id)
        if mission is None:
            return {"status": "missing", "mission_id": mission_id}
        graph = self.missions.graph_for_mission(mission_id, self.db.path)
        requested = list(task_ids) if task_ids is not None else [
            str(node["id"]) for node in graph.get("nodes", [])
            if node.get("status") == "failed"
        ]
        approved: set[str] = set()
        safe: list[str] = []
        blocked: list[dict] = []
        risk_order = {"safe": 0, "local_write": 1, "external": 2, "financial": 3}

        for task_id in requested:
            row = self.db.get_task(task_id)
            if not row:
                blocked.append({"task_id": task_id, "reason": "task_missing"})
                continue
            payload = json.loads(row["payload"] or "{}")
            contract = self.workforce.capability_for(row["capability"])
            payload_risk = str(payload.get("risk", "safe")).lower()
            effective_risk = max(
                risk_order.get(payload_risk, 0),
                risk_order.get(str(contract.risk).lower(), 0),
            )
            if effective_risk >= risk_order["external"] and not approve_external:
                blocked.append({
                    "task_id": task_id,
                    "reason": "operator_approval_required",
                    "risk": "financial" if effective_risk == risk_order["financial"] else "external",
                })
                continue
            safe.append(task_id)
            if effective_risk >= risk_order["external"]:
                approved.add(task_id)

        result = self.missions.resume_failed_tasks(
            mission_id,
            self.db.path,
            task_ids=safe,
            approved_task_ids=approved,
            reason="operator_resume",
        )
        result["blocked"] = blocked
        result["approve_external"] = bool(approve_external)
        result["requested"] = requested
        return result

    def approve(self, task_id: str):
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Unknown task: {task_id}")
        if task["status"] != "blocked":
            return {"status": task["status"], "changed": False}
        approved_payload = json.loads(task["payload"])
        approved_payload["approved"] = True
        approved_payload["approved_by"] = "operator"
        now = now_iso()
        self.db.update_task_payload(task_id, approved_payload, now)
        self.db.update_task(task_id, "queued", now)
        self.db.add_event(task_id, "task.approved", {"by": "operator"}, now)
        mission_id = str(approved_payload.get("mission_id") or "").strip()
        if mission_id:
            self.missions.update_from_task(
                mission_id,
                task_id,
                "queued",
                {"approval_granted": True, "approved_by": "operator"},
                task_db=self.db.path,
            )
            self.missions.add_timeline_event(
                mission_id,
                "mission.approval_granted",
                {"approved_by": "operator"},
                task_id=task_id,
                status="queued",
            )
            self.missions.add_audit_event(
                mission_id,
                "task.approve",
                actor="operator",
                task_id=task_id,
                payload={"approved_by": "operator"},
            )
        return {"status": "queued", "changed": True, "mission_id": mission_id or None}

    def approve_mission(
        self,
        mission_id: str,
        task_ids: list[str] | None = None,
    ) -> dict:
        mission = self.missions.get(mission_id)
        if mission is None:
            return {"status": "missing", "mission_id": mission_id}
        graph = self.missions.graph_for_mission(mission_id, self.db.path)
        nodes = {str(node["id"]): node for node in graph.get("nodes", [])}
        requested = list(task_ids) if task_ids is not None else [
            node_id for node_id, node in nodes.items() if node.get("status") == "blocked"
        ]
        approved = []
        skipped = []
        for task_id in requested:
            node = nodes.get(task_id)
            if not node or node.get("status") != "blocked":
                skipped.append({"task_id": task_id, "reason": "not_blocked_or_not_in_mission"})
                continue
            result = self.approve(task_id)
            if result.get("changed"):
                approved.append(task_id)
            else:
                skipped.append({"task_id": task_id, "reason": "not_approvable", "status": result.get("status")})
        self.missions.reconcile(self.db.path)
        refreshed = self.missions.get(mission_id) or mission
        return {
            "mission_id": mission_id,
            "status": refreshed["status"],
            "approved": approved,
            "skipped": skipped,
        }

    def cancel_mission(
        self,
        mission_id: str,
        task_ids: list[str] | None = None,
        reason: str = "operator_cancel",
    ) -> dict:
        return self.missions.cancel_mission(
            mission_id,
            self.db.path,
            task_ids=task_ids,
            reason=reason,
        )

    def tasks(self):
        return [dict(r) for r in self.db.list_tasks()]

    def close(self):
        self.missions.close()
        self.db.close()
