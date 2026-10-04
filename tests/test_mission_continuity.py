from oth.core.console_store import ConsoleStore
from oth.core.mission_state import MissionStateStore


def test_mission_state_creates_and_reads(tmp_path):
    store = MissionStateStore(tmp_path / "console.db")
    try:
        mission = store.create(
            "conversation-1",
            "Build the memory subsystem",
            "design -> implement -> verify",
            mission_id="mission-1",
        )
        store.attach_root_tasks("mission-1", ["task-1"])
        current = store.get("mission-1")
        assert mission["status"] == "queued"
        assert current["root_task_ids"] == ["task-1"]
        assert current["conversation_id"] == "conversation-1"
    finally:
        store.close()


def test_mission_state_queued_to_succeeded(tmp_path):
    store = MissionStateStore(tmp_path / "console.db")
    try:
        store.create("conversation-1", "Build", "verify", mission_id="mission-1")
        store.attach_root_tasks("mission-1", ["task-1"])
        result = store.update_from_task(
            "mission-1",
            "task-1",
            "succeeded",
            {"summary": "implemented"},
        )
        assert result["status"] == "succeeded"
        assert result["latest_outcome"]["summary"] == "implemented"
        assert result["completed_at"]
    finally:
        store.close()


def test_mission_state_queued_to_failed(tmp_path):
    store = MissionStateStore(tmp_path / "console.db")
    try:
        store.create("conversation-1", "Build", "verify", mission_id="mission-1")
        store.attach_root_tasks("mission-1", ["task-1"])
        result = store.update_from_task(
            "mission-1",
            "task-1",
            "failed",
            {"error": "verification failed"},
        )
        assert result["status"] == "failed"
        assert result["latest_outcome"]["error"] == "verification failed"
        assert result["completed_at"]
    finally:
        store.close()


def test_console_context_includes_durable_mission_state(tmp_path):
    store = ConsoleStore(tmp_path / "console.db")
    try:
        store.create_conversation("conversation-1")
        store.missions.create(
            "conversation-1",
            "Build persistent mission continuity",
            "persist -> resume",
            mission_id="mission-1",
        )
        store.missions.attach_root_tasks("mission-1", ["task-1"])
        context = store.context_for_model(
            "conversation-1",
            "resume the previous mission",
            recent=2,
            retrieved=2,
            memories=2,
        )
        joined = "\n".join(item["content"] for item in context)
        assert "DURABLE OTH MISSION STATE" in joined
        assert "Build persistent mission continuity" in joined
        assert "mission-1" in joined
    finally:
        store.close()
