from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PilotTaskSpec:
    capability: str
    action: str
    payload: dict[str, Any]
    priority: int = 70


@dataclass(frozen=True)
class PilotPlan:
    goal: str
    strategy: str
    tasks: tuple[PilotTaskSpec, ...]


class PilotPlanner:
    """Deterministic first-line goal router; specialists remain replaceable workers."""

    ROUTES = (
        (("research", "find", "market", "demand", "problem", "opportunit"), "research"),
        (("review", "complaint", "friction"), "review"),
        (("analytics", "metrics", "performance"), "analytics"),
        (("content", "post", "copy", "script"), "content"),
        (("social", "linkedin", "instagram", "youtube", "twitter", "x "), "social"),
        (("transcrib", "subtitle", "caption"), "transcription"),
        (("edit", "editing", "render", "video", "media"), "media"),
        (("resolve",), "resolve"),
        (("build", "automation", "workflow", "saas", "product"), "build"),
    )

    def plan(self, instruction: str) -> PilotPlan:
        text = instruction.strip()
        lowered = f" {text.lower()} "
        route = "reasoning"
        for keywords, candidate in self.ROUTES:
            if any(keyword in lowered for keyword in keywords):
                route = candidate
                break

        if route == "research":
            task = PilotTaskSpec(
                "scout",
                "scan",
                {
                    "queries": [
                        text,
                        f"{text} complaints problems alternatives",
                        f"{text} manual workflow software",
                    ],
                    "risk": "safe",
                    "max_retries": 1,
                    "next": [{
                        "capability": "review-mining",
                        "action": "mine",
                        "priority": 68,
                        "payload": {"input_from": "event.output"},
                    }],
                },
                75,
            )
            return PilotPlan(text, "research -> review mining -> analysis -> automation pipeline", (task,))

        if route == "review":
            return PilotPlan(
                text,
                "evidence discovery -> review mining -> opportunity analysis",
                (
                    PilotTaskSpec(
                        "scout",
                        "scan",
                        {
                            "queries": [
                                text,
                                f"{text} complaints reviews alternatives",
                                f"{text} negative reviews pain points",
                            ],
                            "risk": "safe",
                            "max_retries": 1,
                            "next": [{
                                "capability": "review-mining",
                                "action": "mine",
                                "priority": 68,
                                "payload": {"input_from": "event.output"},
                            }],
                        },
                        70,
                    ),
                ),
            )

        if route == "analytics":
            return PilotPlan(
                text,
                "analytics synchronization -> optimization",
                (
                    PilotTaskSpec("social-analytics", "sync", {"input": {}, "risk": "safe"}, 65),
                    PilotTaskSpec("social-optimization", "optimize", {"input": {}, "risk": "safe"}, 64),
                ),
            )

        if route == "content":
            return PilotPlan(
                text,
                "content strategy through the existing social/content workforce",
                (
                    PilotTaskSpec(
                        "social-content",
                        "create",
                        {"input": {"brief": text, "privacy_status": "private_by_default"}, "risk": "safe"},
                        70,
                    ),
                ),
            )

        if route == "social":
            return PilotPlan(
                text,
                "social specialist execution under OTH policy",
                (
                    PilotTaskSpec(
                        "social-autonomy",
                        "command",
                        {"input": {"instruction": text}, "risk": "safe"},
                        80,
                    ),
                ),
            )

        if route == "transcription":
            return PilotPlan(
                text,
                "media transcription worker",
                (
                    PilotTaskSpec(
                        "media-transcription",
                        "transcribe",
                        {"input": {"instruction": text}, "risk": "safe"},
                        72,
                    ),
                ),
            )

        if route == "media":
            return PilotPlan(
                text,
                "media production worker",
                (
                    PilotTaskSpec(
                        "media-production",
                        "plan",
                        {"input": {"brief": text}, "risk": "local_write"},
                        72,
                    ),
                ),
            )

        if route == "resolve":
            return PilotPlan(
                text,
                "Resolve bridge dependency-aware execution",
                (
                    PilotTaskSpec(
                        "resolve-bridge",
                        "status",
                        {"input": {}, "risk": "safe"},
                        72,
                    ),
                ),
            )

        if route == "build":
            task = PilotTaskSpec(
                "scout",
                "scan",
                {
                    "queries": [
                        text,
                        f"{text} competitors complaints alternatives",
                        f"{text} manual workflow demand",
                    ],
                    "risk": "safe",
                    "max_retries": 1,
                    "next": [{
                        "capability": "review-mining",
                        "action": "mine",
                        "priority": 68,
                        "payload": {"input_from": "event.output"},
                    }],
                },
                76,
            )
            return PilotPlan(text, "discover -> validate -> design -> build -> QA -> promotion", (task,))

        return PilotPlan(
            text,
            "general reasoning worker; OTH remains the orchestrator",
            (
                PilotTaskSpec(
                    "reasoning",
                    "prompt",
                    {
                        "prompt": (
                            "Act as a reasoning specialist inside Over The Horizon. "
                            "Turn this operator goal into a concise, actionable task decomposition "
                            "without executing external actions: "
                            + text
                        ),
                        "risk": "safe",
                        "max_retries": 1,
                    },
                    60,
                ),
            ),
        )

    def submit(self, kernel, instruction: str) -> dict[str, Any]:
        plan = self.plan(instruction)
        root_ids = []
        for spec in plan.tasks:
            task = kernel.submit(
                spec.capability,
                spec.action,
                dict(spec.payload),
                spec.priority,
            )
            root_ids.append(task.id)
        return {
            "goal": plan.goal,
            "strategy": plan.strategy,
            "root_task_ids": root_ids,
            "task_count": len(root_ids),
        }
