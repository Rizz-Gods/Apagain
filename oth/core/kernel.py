import uuid
from pathlib import Path
from .db import Database
from .models import Task, now_iso
from .policy import PolicyGate
from .registry import Registry
from .analyst import OpportunityAnalyst
from .automation_builder import AutomationBuilder
from .automation_designer import AutomationDesigner
from .dependency_provisioner import DependencyProvisioner
from .promotion_gate import PromotionGate
from .workflow_compiler import WorkflowCompiler
from .qa_validator import QAValidator
from .review_miner import ReviewMiner
from .skills import SkillAcquirer
from .tools import ToolRegistry
from oth.workers.browser import BrowserWorker
from oth.workers.builtin import BuiltinWorker
from oth.workers.external import ExternalAgentWorker
from oth.core.scout import ScoutWorker
from oth.core.social_market import SocialMarketWorker
from oth.core.social_accounts import SocialAccountManager
from oth.core.social_content import SocialContentEngine
from oth.core.social_leads import SocialLeadEngine
from oth.core.social_autopilot import SocialAutopilot
from oth.core.social_queue import SocialQueueManager
from oth.core.social_optimizer import SocialOptimizer
from oth.core.social_actions import SocialActionBus

class OTHKernel:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.db = Database(self.root / "data" / "oth.db")
        self.registry = Registry(
            self.root / "config" / "agents.json",
            self.root / "config" / "skills.json",
        )
        self.skill_acquirer = SkillAcquirer(self.root)
        self.policy = PolicyGate(self.root / "config" / "policies.json")
        self.tools = ToolRegistry(self.root / "config" / "tools.json")
        self.workers = [BuiltinWorker()]
        modes = set()
        for agent in self.registry.load_agents():
            mode = agent.metadata.get("mode")
            if mode == "browser":
                self.workers.append(BrowserWorker(agent))
            elif mode == "scout":
                self.workers.append(ScoutWorker(agent))
                modes.add("scout")
            elif mode == "analysis":
                self.workers.append(OpportunityAnalyst())
                modes.add("analysis")
            elif mode == "review-mining":
                self.workers.append(ReviewMiner(agent))
                modes.add("review-mining")
            elif mode == "automation-design":
                self.workers.append(AutomationDesigner())
                modes.add("automation-design")
            elif mode == "automation-build":
                self.workers.append(AutomationBuilder(self.root))
                modes.add("automation-build")
            elif mode == "qa":
                self.workers.append(QAValidator(self.root))
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
            elif mode == "social-actions":
                self.workers.append(SocialActionBus(self.root))
                modes.add("social-actions")
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
        if "social-actions" not in modes:
            self.workers.append(SocialActionBus(self.root))

    def submit(self, capability: str, action: str, payload: dict, priority: int = 50) -> Task:
        task = Task(str(uuid.uuid4()), capability, action, payload, priority)
        self.db.add_task(task)
        self.db.add_event(task.id, "task.queued",
                          {"capability": capability, "action": action},
                          task.created_at)
        return task

    def dispatch(self, task_id: str):
        rows = [r for r in self.db.list_tasks() if r["id"] == task_id]
        if not rows:
            raise ValueError(f"Unknown task: {task_id}")
        row = rows[0]
        import json
        stored_payload = json.loads(row["payload"])
        task_payload = dict(stored_payload)
        if task_payload.get("prompt"):
            task_payload["skill_context"] = self.skill_acquirer.context_for(task_payload["prompt"])
            memories = self.db.recent_memories(row["capability"], 5)
            task_payload["memory_context"] = "\n".join(
                f'{m["created_at"]}: {m["content"]}' for m in memories
            )
        if row["capability"] == "social-actions" and row["action"] in {"publish_text"}:
            task_payload["risk"] = "external"
        decision = self.policy.check(task_payload)
        if not decision.allowed:
            self.db.update_task(task_id, "blocked", now_iso())
            self.db.add_event(task_id, "task.approval_required", {"reason": decision.reason}, now_iso())
            return {"status": "blocked", "reason": decision.reason}
        self.db.update_task(task_id, "running", now_iso())
        self.db.add_event(task_id, "task.started", {}, now_iso())
        candidates = [w for w in self.workers if w.supports(row["capability"])]
        candidates.sort(
            key=lambda w: (
                float(getattr(w, "agent", None).metadata.get("priority", 50))
                if getattr(w, "agent", None) else 50
            )
            + self.db.agent_health(getattr(w, "id", "builtin"))["reliability"] * 10,
            reverse=True,
        )
        worker = candidates[0] if candidates else None
        if worker is None:
            self.db.update_task(task_id, "blocked", now_iso())
            self.db.add_event(task_id, "task.blocked", {"reason": "no_worker"}, now_iso())
            return {"status": "blocked", "reason": "no_worker"}

        import json
        result = worker.execute(row["action"], task_payload)
        status = "succeeded" if result.success else "failed"
        retry_scheduled = False
        if (not result.success and result.retryable
                and int(stored_payload.get("_attempts", 0))
                < int(stored_payload.get("max_retries", 0))):
            stored_payload["_attempts"] = int(stored_payload.get("_attempts", 0)) + 1
            self.db.update_task_payload(task_id, stored_payload, now_iso())
            self.db.update_task(task_id, "queued", now_iso())
            self.db.add_event(
                task_id, "task.retry_scheduled",
                {"attempt": stored_payload["_attempts"]}, now_iso(),
            )
            retry_scheduled = True
        if not retry_scheduled:
            self.db.update_task(task_id, status, now_iso())
        worker_id = getattr(worker, "id", "builtin")
        self.db.record_agent_result(
            worker_id,
            result.success,
            result.error,
            now_iso(),
        )
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
                "output": result.output,
                "retryable": result.retryable,
            },
            now_iso(),
        )
        self.db.add_event(task_id, f"task.{effective_status}",
                          {"output": result.output, "error": result.error,
                           "retryable": result.retryable},
                          now_iso())
        spawned = []
        if result.success:
            handoffs = task_payload.get("next") or result.output.get("next") or []
            for spec in handoffs:
                child_payload = dict(spec.get("payload", {}))
                if "input" not in child_payload:
                    child_payload["input"] = result.output
                child = self.submit(
                    spec["capability"],
                    spec["action"],
                    child_payload,
                    int(spec.get("priority", 50)),
                )
                spawned.append(child.id)
                self.db.add_event(
                    task_id, "task.spawned",
                    {"child_task_id": child.id, "capability": child.capability},
                    now_iso(),
                )
        return {"status": effective_status, **result.output,
                "error": result.error, "spawned": spawned,
                "retryable": result.retryable}

    def approve(self, task_id: str):
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Unknown task: {task_id}")
        if task["status"] != "blocked":
            return {"status": task["status"], "changed": False}
        import json
        approved_payload = json.loads(task["payload"])
        approved_payload["approved"] = True
        approved_payload["approved_by"] = "operator"
        now = now_iso()
        self.db.update_task_payload(task_id, approved_payload, now)
        self.db.update_task(task_id, "queued", now)
        self.db.add_event(task_id, "task.approved", {"by": "operator"}, now)
        return {"status": "queued", "changed": True}

    def tasks(self):
        return [dict(r) for r in self.db.list_tasks()]

    def close(self):
        self.db.close()
