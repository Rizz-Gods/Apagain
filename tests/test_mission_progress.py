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


def test_mission_progress_reports_partial_completion_and_eta(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create(
            "conversation-1",
            "Progress mission",
            "work -> verify",
            mission_id="mission-progress",
        )
        first = kernel.submit(
            "demo",
            "echo",
            {"message": "done", "mission_id": "mission-progress"},
            50,
        )
        second = kernel.submit(
            "demo",
            "echo",
            {"message": "active", "mission_id": "mission-progress"},
            50,
        )
        missions.attach_root_tasks("mission-progress", [first.id, second.id])

        kernel.db.conn.execute(
            "UPDATE tasks SET created_at=?, updated_at=?, status='succeeded' WHERE id=?",
            (
                "2026-10-05T08:00:00+00:00",
                "2026-10-05T08:01:00+00:00",
                first.id,
            ),
        )
        kernel.db.conn.execute(
            "UPDATE tasks SET created_at=?, updated_at=?, status='queued' WHERE id=?",
            (
                "2026-10-05T08:00:30+00:00",
                "2026-10-05T08:01:00+00:00",
                second.id,
            ),
        )
        kernel.db.conn.commit()

        progress = missions.progress_for_mission("mission-progress", kernel.db.path)
        assert progress["total"] == 2
        assert progress["completed"] == 1
        assert progress["succeeded"] == 1
        assert progress["active"] == 1
        assert progress["percent"] == 50.0
        assert progress["average_cycle_seconds"] == 60.0
        assert progress["eta_seconds"] == 60.0
        assert progress["eta_confidence"] == "observed_cycle"
    finally:
        kernel.close()
        missions.close()


def test_mission_progress_without_history_does_not_invent_eta(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create(
            "conversation-1",
            "No history",
            "queue",
            mission_id="mission-progress-empty",
        )
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "queued", "mission_id": "mission-progress-empty"},
            50,
        )
        missions.attach_root_tasks("mission-progress-empty", [task.id])
        progress = missions.progress_for_mission(
            "mission-progress-empty",
            kernel.db.path,
        )
        assert progress["total"] == 1
        assert progress["completed"] == 0
        assert progress["percent"] == 0.0
        assert progress["eta_seconds"] is None
        assert progress["eta_confidence"] == "insufficient_history"
    finally:
        kernel.close()
        missions.close()
