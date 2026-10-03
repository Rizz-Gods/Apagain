import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.core.pilot import PilotPlanner
from oth.core.workforce import WorkforceRegistry


def write_minimal_config(root: Path, agents: str = '{"agents":[]}'):
    (root / "config").mkdir()
    (root / "data").mkdir()
    (root / "config" / "agents.json").write_text(agents, encoding="utf-8")
    (root / "config" / "skills.json").write_text('{"skills":[]}', encoding="utf-8")
    (root / "config" / "policies.json").write_text(
        '{"external_actions_require_approval":true,"financial_actions_require_approval":true}',
        encoding="utf-8",
    )
    (root / "config" / "tools.json").write_text('{"tools":[]}', encoding="utf-8")


class WorkforceControlPlaneTests(unittest.TestCase):
    def test_workforce_contract_and_capability_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agents = (
                '{"agents":[{"id":"worker-a","name":"Worker A",'
                '"capabilities":["special"],"status":"available",'
                '"metadata":{"priority":90}}]}'
            )
            write_minimal_config(root, agents)
            (root / "config" / "workforce.json").write_text(
                '{"capabilities":{"special":{"department":"research",'
                '"required_permissions":["research"]}},'
                '"workers":{"worker-a":{"permissions":["read","research"],'
                '"department":"research"}}}',
                encoding="utf-8",
            )
            registry = WorkforceRegistry(root)
            contract = registry.contract_for("worker-a")
            capability = registry.capability_for("special")
            candidates = registry.resolve_candidates("special")
            self.assertEqual(contract.department, "research")
            self.assertIn("research", capability.required_permissions)
            self.assertEqual([x.worker_id for x in candidates], ["worker-a"])

    def test_event_trigger_spawns_durable_follow_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_config(root)
            (root / "config" / "triggers.json").write_text(
                '{"triggers":[{"id":"demo-follow-up","enabled":true,'
                '"event":{"kind":"task.succeeded","capability":"demo"},'
                '"tasks":[{"capability":"demo","action":"echo","priority":40,'
                '"payload":{"input_from":"event.output","risk":"safe"}}]}]}',
                encoding="utf-8",
            )
            kernel = OTHKernel(root)
            first = kernel.submit("demo", "echo", {"message": "hello"})
            result = kernel.dispatch(first.id)
            self.assertEqual(result["status"], "succeeded")
            tasks = kernel.tasks()
            self.assertEqual(len(tasks), 2)
            child = next(task for task in tasks if task["id"] != first.id)
            self.assertEqual(child["status"], "queued")
            self.assertEqual(child["capability"], "demo")
            self.assertEqual(child["action"], "echo")
            kernel.close()

    def test_pilot_research_plan_builds_a_task_graph_root(self):
        plan = PilotPlanner().plan("find demand for appointment scheduling software")
        self.assertEqual(plan.tasks[0].capability, "scout")
        self.assertEqual(plan.tasks[0].action, "scan")
        self.assertEqual(plan.tasks[0].payload["next"][0]["capability"], "review-mining")

    def test_pilot_review_plan_starts_with_evidence_collection(self):
        plan = PilotPlanner().plan("find complaints and reviews about appointment scheduling")
        self.assertEqual(plan.tasks[0].capability, "scout")
        self.assertEqual(plan.tasks[0].action, "scan")
        self.assertEqual(plan.tasks[0].payload["next"][0]["action"], "mine")


if __name__ == "__main__":
    unittest.main()
