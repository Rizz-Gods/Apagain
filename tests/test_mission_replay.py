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


def test_replay_merges_timeline_and_audit_in_deterministic_order(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("conversation-1", "Replay mission", "merge evidence", mission_id="mission-replay")
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "hello", "mission_id": "mission-replay"},
            50,
        )
        store.attach_root_tasks("mission-replay", [task.id])
        store.add_timeline_event(
            "mission-replay",
            "mission.task_updated",
            {"aggregate_status": "queued"},
            task_id=task.id,
            status="queued",
            created_at="2026-10-05T10:00:01+00:00",
        )
        kernel.db.add_event(
            task.id,
            "task.started",
            {"worker_id": "demo"},
            "2026-10-05T10:00:02+00:00",
        )
        store.add_audit_event(
            "mission-replay",
            "task.approve",
            actor="operator",
            task_id=task.id,
            created_at="2026-10-05T10:00:03+00:00",
        )

        replay = store.replay_for_mission(
            "mission-replay",
            kernel.db.path,
        )
        assert replay["audit_integrity"]["valid"] is True
        assert replay["audit_count"] == 2
        assert replay["timeline_count"] >= 2
        assert replay["replay_count"] >= 4
        timestamps = [item["created_at"] for item in replay["replay"]]
        assert timestamps == sorted(timestamps)
        assert any(item["source"] == "task_event" for item in replay["replay"])
        assert any(item["source"] == "audit" for item in replay["replay"])
        assert [item["sequence"] for item in replay["replay"]] == list(range(1, replay["replay_count"] + 1))
    finally:
        kernel.close()
        store.close()


def test_replay_limit_is_bounded(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("conversation-1", "Replay limit", "bounded", mission_id="mission-limit")
        for index in range(12):
            store.add_timeline_event(
                "mission-limit",
                "mission.test",
                {"index": index},
                status="queued",
                created_at=f"2026-10-05T10:00:{index:02d}+00:00",
            )
        replay = store.replay_for_mission("mission-limit", kernel.db.path, limit=5)
        assert replay["replay_count"] == 5
        assert len(replay["replay"]) == 5
        assert replay["replay"][0]["sequence"] == 1
    finally:
        kernel.close()
        store.close()


def test_replay_reports_missing_mission(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        assert store.replay_for_mission("missing", kernel.db.path) is None
    finally:
        kernel.close()
        store.close()


def test_replay_detects_broken_audit_chain(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("conversation-1", "Replay integrity", "detect tamper", mission_id="mission-integrity")
        store.add_audit_event("mission-integrity", "test.event", payload={"value": 1})
        store.db.execute(
            "UPDATE mission_audit SET payload=? WHERE action='test.event'",
            ('{"value":999}',),
        )
        store.db.commit()
        replay = store.replay_for_mission("mission-integrity", kernel.db.path)
        assert replay["audit_integrity"]["valid"] is False
        assert replay["replay_count"] > 0
    finally:
        kernel.close()
        store.close()


def test_control_surface_remains_read_only_and_replay_is_separate(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("conversation-1", "Control replay", "read only", mission_id="mission-control-replay")
        snapshot = store.control_snapshot("mission-control-replay", kernel.db.path)
        assert "replay" not in snapshot
        assert snapshot["audit_integrity"]["valid"] is True
        replay = store.replay_for_mission("mission-control-replay", kernel.db.path)
        assert replay["mission_id"] == "mission-control-replay"
    finally:
        kernel.close()
        store.close()
