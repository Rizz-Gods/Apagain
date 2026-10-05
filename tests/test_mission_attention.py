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


def test_attention_is_created_from_escalation_and_acknowledge_is_durable(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        store.create(
            "conversation-1",
            "Attention mission",
            "deadline -> alert",
            mission_id="mission-attention",
        )
        store.set_deadline(
            "mission-attention",
            "2020-01-01T00:00:00+00:00",
        )
        open_items = store.attention_for_mission("mission-attention")
        assert len(open_items) == 1
        assert open_items[0]["severity"] == "critical"
        assert open_items[0]["kind"] == "mission.deadline_exceeded"

        event_count = len(store.timeline_for_mission("mission-attention"))
        store.watchdog_for_mission(
            "mission-attention",
            None,
            now="2026-10-05T10:00:00+00:00",
        )
        assert len(store.attention_for_mission("mission-attention")) == 1
        assert len(store.timeline_for_mission("mission-attention")) == event_count

        item_id = open_items[0]["id"]
        ack = store.acknowledge_attention(item_id, "operator")
        assert ack["status"] == "acknowledged"
        assert ack["acknowledged_by"] == "operator"
        assert store.attention_for_mission("mission-attention") == []
        assert store.attention_for_mission(
            "mission-attention",
            include_acknowledged=True,
        )[0]["id"] == item_id
    finally:
        store.close()


def test_control_snapshot_exposes_open_attention(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create(
            "conversation-1",
            "Blocked attention mission",
            "block -> operator",
            mission_id="mission-attention-blocked",
        )
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "blocked", "mission_id": "mission-attention-blocked"},
            50,
        )
        store.attach_root_tasks("mission-attention-blocked", [task.id])
        kernel.db.update_task(task.id, "blocked", "2026-10-05T10:00:00+00:00")
        store.update_from_task(
            "mission-attention-blocked",
            task.id,
            "blocked",
            {"error": "operator approval required", "approval_required": True},
            task_db=kernel.db.path,
        )

        snapshot = store.control_snapshot(
            "mission-attention-blocked",
            kernel.db.path,
        )
        assert snapshot["attention_open_count"] == 1
        assert snapshot["attention"][0]["severity"] == "critical"
        assert snapshot["attention"][0]["task_id"] == task.id
    finally:
        kernel.close()
        store.close()


def test_attention_list_can_filter_by_mission_and_include_acknowledged(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        store.create("conversation-1", "A", "alert", mission_id="mission-a")
        store.create("conversation-1", "B", "alert", mission_id="mission-b")
        store.add_timeline_event(
            "mission-a",
            "mission.escalation_warning",
            {"seconds_to_deadline": 90},
            status="queued",
        )
        store.add_timeline_event(
            "mission-b",
            "mission.escalation_critical",
            {"seconds_to_deadline": 30},
            status="queued",
        )

        assert len(store.list_attention(mission_id="mission-a")) == 1
        assert len(store.list_attention()) == 2

        first = store.list_attention(mission_id="mission-a")[0]
        store.acknowledge_attention(first["id"])
        assert len(store.list_attention()) == 1
        assert len(store.list_attention(include_acknowledged=True)) == 2
    finally:
        store.close()
