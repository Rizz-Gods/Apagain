import json
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.core.mission_state import MissionStateStore


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


def test_queued_mission_task_cancels_and_dispatch_honors_cancelled_state(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create(
            "conversation-1",
            "Cancel queued mission",
            "queue -> cancel",
            mission_id="mission-cancel-queued",
        )
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "cancel-me", "mission_id": "mission-cancel-queued", "max_retries": 0},
            50,
        )
        missions.attach_root_tasks("mission-cancel-queued", [task.id])

        result = kernel.cancel_mission("mission-cancel-queued")
        assert result["cancelled"] == [task.id]
        assert result["cancellation_requested"] == []
        assert result["status"] == "cancelled"
        assert kernel.db.get_task(task.id)["status"] == "cancelled"
        assert kernel.dispatch(task.id)["status"] == "cancelled"

        snapshot = missions.control_snapshot("mission-cancel-queued", kernel.db.path)
        assert snapshot["graph"]["counts"]["cancelled"] == 1
        actions = {item["action"]: item for item in snapshot["actions"]}
        assert actions["cancel"]["enabled"] is False
        assert "mission.task_cancelled" in [item["kind"] for item in snapshot["timeline"]]
    finally:
        kernel.close()
        missions.close()


def test_blocked_mission_task_can_be_cancelled_without_approval(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create(
            "conversation-1",
            "Cancel blocked mission",
            "blocked -> cancel",
            mission_id="mission-cancel-blocked",
        )
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "blocked", "mission_id": "mission-cancel-blocked", "max_retries": 0},
            50,
        )
        missions.attach_root_tasks("mission-cancel-blocked", [task.id])
        kernel.db.update_task(task.id, "blocked", "2026-10-05T00:00:00+00:00")
        missions.update_from_task(
            "mission-cancel-blocked",
            task.id,
            "blocked",
            {"approval_required": True},
            task_db=kernel.db.path,
        )

        result = kernel.cancel_mission("mission-cancel-blocked")
        assert result["cancelled"] == [task.id]
        assert kernel.db.get_task(task.id)["status"] == "cancelled"
        assert missions.get("mission-cancel-blocked")["status"] == "cancelled"
    finally:
        kernel.close()
        missions.close()


def test_running_mission_task_receives_graceful_cancellation_request(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create(
            "conversation-1",
            "Gracefully stop running work",
            "running -> cancellation request",
            mission_id="mission-cancel-running",
        )
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "running", "mission_id": "mission-cancel-running", "max_retries": 0},
            50,
        )
        missions.attach_root_tasks("mission-cancel-running", [task.id])
        kernel.db.update_task(task.id, "running", "2026-10-05T00:00:00+00:00")
        missions.update_from_task(
            "mission-cancel-running",
            task.id,
            "running",
            {"summary": "worker currently executing"},
            task_db=kernel.db.path,
        )

        result = kernel.cancel_mission("mission-cancel-running")
        assert result["cancelled"] == []
        assert result["cancellation_requested"] == [task.id]
        assert result["status"] == "running"

        stored = kernel.db.get_task(task.id)
        payload = json.loads(stored["payload"])
        assert stored["status"] == "running"
        assert payload["_cancel_requested"] is True
        assert missions.get("mission-cancel-running")["status"] == "running"

        timeline = missions.timeline_for_mission("mission-cancel-running", task_db=kernel.db.path)
        assert any(item["kind"] == "mission.cancel_requested" for item in timeline)
        assert any(item.get("kind") == "task.cancel_requested" for item in timeline)
    finally:
        kernel.close()
        missions.close()
