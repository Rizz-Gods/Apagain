from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.core.mission_state import MissionStateStore
from oth.workers.builtin import WorkerResult


def write_minimal_config(root: Path):
    (root / "config").mkdir()
    (root / "data").mkdir()
    (root / "config" / "agents.json").write_text('{"agents":[]}', encoding="utf-8")
    (root / "config" / "skills.json").write_text('{"skills":[]}', encoding="utf-8")
    (root / "config" / "policies.json").write_text(
        '{"external_actions_require_approval":true,"financial_actions_require_approval":true}',
        encoding="utf-8",
    )
    (root / "config" / "tools.json").write_text('{"tools":[]}', encoding="utf-8")


def test_budget_policy_persists_and_is_visible_in_control(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("conversation-1", "Budget policy", "guard", mission_id="mission-budget")
        result = store.set_budget(
            "mission-budget",
            max_tasks=3,
            max_retries=2,
            actor="operator",
            task_db=kernel.db.path,
        )
        assert result["max_tasks"] == 3
        assert result["max_retries"] == 2
        snapshot = store.control_snapshot("mission-budget", kernel.db.path)
        assert snapshot["budget"]["max_tasks"] == 3
        assert snapshot["budget"]["max_retries"] == 2
        assert snapshot["budget"]["status"] == "ok"
        assert store.audit_for_mission("mission-budget")[-1]["action"] == "mission.budget.policy_set"
    finally:
        kernel.close()
        store.close()


def test_task_budget_blocks_new_child_tasks(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("conversation-1", "Task cap", "one node", mission_id="mission-task-cap")
        store.set_budget(
            "mission-task-cap",
            max_tasks=1,
            max_retries=8,
            task_db=kernel.db.path,
        )
        root = kernel.submit(
            "demo",
            "echo",
            {"message": "root", "mission_id": "mission-task-cap"},
            50,
        )
        store.attach_root_tasks("mission-task-cap", [root.id])

        child = kernel.submit(
            "demo",
            "echo",
            {"message": "child", "mission_id": "mission-task-cap"},
            40,
        )
        assert child.status == "blocked"
        assert child.payload["_budget_blocked"] is True
        assert store.get("mission-task-cap")["budget_status"] == "tasks_exhausted"
        attention = store.attention_for_mission("mission-task-cap")
        assert any(item["kind"] == "mission.budget_exhausted" for item in attention)
    finally:
        kernel.close()
        store.close()


def test_retry_budget_blocks_dispatch_retry(tmp_path):
    write_minimal_config(tmp_path)

    class AlwaysFailWorker:
        id = "always-fail"

        def supports(self, capability: str) -> bool:
            return capability == "demo"

        def execute(self, action: str, payload):
            return WorkerResult(False, {}, "forced failure", retryable=True)

    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    kernel.workers = [AlwaysFailWorker()]
    try:
        store.create("conversation-1", "Retry cap", "no retry", mission_id="mission-retry-cap")
        store.set_budget(
            "mission-retry-cap",
            max_tasks=10,
            max_retries=0,
            task_db=kernel.db.path,
        )
        task = kernel.submit(
            "demo",
            "echo",
            {
                "message": "fail",
                "mission_id": "mission-retry-cap",
                "max_retries": 1,
            },
            50,
        )
        store.attach_root_tasks("mission-retry-cap", [task.id])
        result = kernel.dispatch(task.id)
        assert result["status"] == "failed"
        assert kernel.db.get_task(task.id)["status"] == "failed"
        assert store.get("mission-retry-cap")["budget_status"] == "retries_exhausted"
        kinds = [
            item["kind"]
            for item in store.timeline_for_mission("mission-retry-cap", task_db=kernel.db.path)
        ]
        assert "mission.budget_exhausted" in kinds
        assert not any(
            row["kind"] == "task.retry_scheduled"
            for row in kernel.db.conn.execute(
                "SELECT kind FROM events WHERE task_id=?",
                (task.id,),
            ).fetchall()
        )
    finally:
        kernel.close()
        store.close()


def test_budget_limits_are_validated(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        store.create("conversation-1", "Validation", "limits", mission_id="mission-validation")
        try:
            store.set_budget("mission-validation", max_tasks=0)
            raise AssertionError("expected max_tasks validation")
        except ValueError as exc:
            assert "max_tasks" in str(exc)

        try:
            store.set_budget("mission-validation", max_retries=-1)
            raise AssertionError("expected max_retries validation")
        except ValueError as exc:
            assert "max_retries" in str(exc)
    finally:
        store.close()


def test_budget_status_does_not_mutate_mission_updated_at_when_unchanged(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("conversation-1", "Stable status", "no churn", mission_id="mission-stable")
        before = store.get("mission-stable")["updated_at"]
        store.update_budget_status("mission-stable", kernel.db.path)
        after = store.get("mission-stable")["updated_at"]
        assert before == after
    finally:
        kernel.close()
        store.close()
