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
    def test_coverage_audit_identifies_resilient_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_config(
                root,
                '{"agents":[{"id":"a","name":"A","capabilities":["alpha"],"status":"available"},'
                '{"id":"b","name":"B","capabilities":["alpha"],"status":"available"},'
                '{"id":"c","name":"C","capabilities":["beta"],"status":"available"}]}',
            )
            (root / "config" / "workforce.json").write_text(
                '{"workers":{"a":{"permissions":["read"]},"b":{"permissions":["read"]},"c":{"permissions":["read"]}}}',
                encoding="utf-8",
            )
            registry = WorkforceRegistry(root)
            report = registry.coverage()
            alpha = next(item for item in report["capabilities"] if item["capability"] == "alpha")
            beta = next(item for item in report["capabilities"] if item["capability"] == "beta")
            self.assertTrue(alpha["resilient"])
            self.assertTrue(alpha["worker_count"] == 2)
            self.assertFalse(beta["resilient"])
            self.assertEqual(report["single_point_count"], 1)

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
            graph = kernel.db.task_graph(first.id)
            self.assertEqual(len(graph["edges"]), 1)
            self.assertEqual(graph["edges"][0]["edge_type"], "trigger")
            kernel.close()

    def test_task_graph_persists_handoff_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_config(root)
            kernel = OTHKernel(root)
            try:
                first = kernel.submit(
                    "demo",
                    "echo",
                    {
                        "message": "hello",
                        "max_retries": 0,
                        "next": [
                            {
                                "capability": "demo",
                                "action": "echo",
                                "priority": 40,
                                "edge_type": "handoff",
                            }
                        ],
                    },
                )
                result = kernel.dispatch(first.id)
                self.assertEqual(result["status"], "succeeded")
                graph = kernel.db.task_graph(first.id)
                self.assertEqual(graph["root"], first.id)
                self.assertEqual(len(graph["nodes"]), 2)
                self.assertEqual(len(graph["edges"]), 1)
                self.assertEqual(graph["edges"][0]["parent_task_id"], first.id)
                self.assertEqual(graph["edges"][0]["edge_type"], "handoff")
            finally:
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
