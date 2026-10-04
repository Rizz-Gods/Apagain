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


def test_kernel_updates_mission_on_root_success(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create("conversation-1", "Echo mission", "execute", mission_id="mission-1")
        task = kernel.submit(
            "demo",
            "echo",
            {
                "message": "hello",
                "mission_id": "mission-1",
                "max_retries": 0,
            },
            50,
        )
        missions.attach_root_tasks("mission-1", [task.id])
        result = kernel.dispatch(task.id)
        assert result["status"] == "succeeded"
        state = missions.get("mission-1")
        assert state["status"] == "succeeded"
        assert state["latest_task_id"] == task.id
    finally:
        kernel.close()
        missions.close()


def test_kernel_updates_mission_on_root_failure(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create("conversation-1", "Fail mission", "execute", mission_id="mission-2")
        task = kernel.submit(
            "demo",
            "unsupported",
            {
                "mission_id": "mission-2",
                "max_retries": 0,
            },
            50,
        )
        missions.attach_root_tasks("mission-2", [task.id])
        result = kernel.dispatch(task.id)
        assert result["status"] == "failed"
        state = missions.get("mission-2")
        assert state["status"] == "failed"
        assert state["latest_task_id"] == task.id
    finally:
        kernel.close()
        missions.close()


def test_pilot_metadata_reaches_task_payload(tmp_path):
    write_minimal_config(tmp_path)
    kernel = OTHKernel(tmp_path)
    try:
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "hello", "mission_id": "mission-3", "conversation_id": "conversation-1"},
            50,
        )
        stored = kernel.db.get_task(task.id)
        payload = json.loads(stored["payload"])
        assert payload["mission_id"] == "mission-3"
        assert payload["conversation_id"] == "conversation-1"
    finally:
        kernel.close()
