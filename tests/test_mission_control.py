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


def test_mission_control_snapshot_exposes_graph_timeline_and_actions(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create(
            "conversation-1",
            "Control mission",
            "execute -> observe -> recover",
            mission_id="mission-control",
        )
        task = kernel.submit(
            "demo",
            "echo",
            {
                "message": "control",
                "mission_id": "mission-control",
                "conversation_id": "conversation-1",
                "max_retries": 0,
            },
            50,
        )
        missions.attach_root_tasks("mission-control", [task.id])
        kernel.db.update_task(task.id, "failed", "2026-10-05T00:00:00+00:00")
        missions.update_from_task(
            "mission-control",
            task.id,
            "failed",
            {"error": "control-test"},
            task_db=kernel.db.path,
        )

        snapshot = missions.control_snapshot(
            "mission-control",
            kernel.db.path,
            timeline_limit=50,
        )
        assert snapshot["mission"]["status"] == "failed"
        assert snapshot["graph"]["counts"]["failed"] == 1
        assert snapshot["timeline"]
        actions = {item["action"]: item for item in snapshot["actions"]}
        assert actions["resume"]["enabled"] is True
        assert actions["resume"]["task_ids"] == [task.id]
        assert actions["approve"]["enabled"] is False
        assert actions["refresh"]["enabled"] is True
    finally:
        kernel.close()
        missions.close()


def test_mission_control_snapshot_exposes_approval_action_for_blocked_task(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create(
            "conversation-1",
            "Approval control mission",
            "block -> approve",
            mission_id="mission-control-approval",
        )
        task = kernel.submit(
            "demo",
            "echo",
            {
                "message": "approval-control",
                "mission_id": "mission-control-approval",
                "max_retries": 0,
            },
            50,
        )
        missions.attach_root_tasks("mission-control-approval", [task.id])
        kernel.db.update_task(task.id, "blocked", "2026-10-05T00:00:00+00:00")
        missions.update_from_task(
            "mission-control-approval",
            task.id,
            "blocked",
            {"approval_required": True},
            task_db=kernel.db.path,
        )

        snapshot = missions.control_snapshot(
            "mission-control-approval",
            kernel.db.path,
        )
        actions = {item["action"]: item for item in snapshot["actions"]}
        assert snapshot["mission"]["status"] == "blocked"
        assert actions["approve"]["enabled"] is True
        assert actions["approve"]["task_ids"] == [task.id]
        assert actions["resume"]["enabled"] is False
    finally:
        kernel.close()
        missions.close()
