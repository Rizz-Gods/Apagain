from pathlib import Path
import json

from oth.core.kernel import OTHKernel
from oth.core.mission_state import MissionStateStore
from oth.core.runner import OTHRunner


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


def test_deadline_watchdog_marks_active_mission_overdue(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        missions.create(
            "conversation-1",
            "Deadline mission",
            "execute -> observe",
            mission_id="mission-deadline",
        )

        state = missions.set_deadline(
            "mission-deadline",
            "2020-01-01T00:00:00+00:00",
        )
        assert state["deadline_at"].startswith("2020-01-01")
        assert state["watchdog_status"] == "overdue"
        assert state["latest_outcome"]["deadline_exceeded"].startswith("2020-01-01")

        timeline = missions.timeline_for_mission("mission-deadline")
        kinds = [item["kind"] for item in timeline]
        assert "mission.deadline_set" in kinds
        assert "mission.deadline_exceeded" in kinds
    finally:
        missions.close()


def test_deadline_clear_removes_watchdog_state(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        missions.create(
            "conversation-1",
            "Clear deadline",
            "set -> clear",
            mission_id="mission-deadline-clear",
        )
        missions.set_deadline(
            "mission-deadline-clear",
            "2020-01-01T00:00:00+00:00",
        )
        state = missions.set_deadline("mission-deadline-clear", None)
        assert state["deadline_at"] is None
        assert state["watchdog_status"] == "ok"

        timeline = missions.timeline_for_mission("mission-deadline-clear")
        assert any(item["kind"] == "mission.deadline_cleared" for item in timeline)
    finally:
        missions.close()


def test_runner_invokes_mission_watchdog(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create(
            "conversation-1",
            "Runner watchdog",
            "watch",
            mission_id="mission-runner-deadline",
        )
        missions.set_deadline(
            "mission-runner-deadline",
            "2099-01-01T00:00:00+00:00",
        )
        missions.db.execute(
            "UPDATE missions SET deadline_at=?, watchdog_status='ok' WHERE id=?",
            ("2020-01-01T00:00:00+00:00", "mission-runner-deadline"),
        )
        missions.db.commit()

        runner = OTHRunner(kernel, interval=0.01)
        result = runner.run_once()
        assert result is None
        state = missions.get("mission-runner-deadline")
        assert state["watchdog_status"] == "overdue"
        assert state["watchdog_checked_at"]
    finally:
        kernel.close()
        missions.close()


def test_deadline_escalation_transitions_are_durable_and_idempotent(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        missions.create(
            "conversation-1",
            "Escalated mission",
            "observe -> intervene",
            mission_id="mission-escalation",
        )
        missions.set_escalation_policy(
            "mission-escalation",
            warning_before_seconds=900,
            critical_before_seconds=300,
        )
        missions.set_deadline(
            "mission-escalation",
            "2026-10-05T12:00:00+00:00",
        )

        state = missions.watchdog_for_mission(
            "mission-escalation",
            None,
            now="2026-10-05T11:40:00+00:00",
        )
        assert state["escalation_level"] == "normal"

        state = missions.watchdog_for_mission(
            "mission-escalation",
            None,
            now="2026-10-05T11:50:00+00:00",
        )
        assert state["escalation_level"] == "warning"
        warning_timeline = missions.timeline_for_mission("mission-escalation")
        assert sum(item["kind"] == "mission.escalation_warning" for item in warning_timeline) == 1

        state = missions.watchdog_for_mission(
            "mission-escalation",
            None,
            now="2026-10-05T11:56:00+00:00",
        )
        assert state["escalation_level"] == "critical"
        assert state["watchdog_status"] == "ok"

        state = missions.watchdog_for_mission(
            "mission-escalation",
            None,
            now="2026-10-05T12:01:00+00:00",
        )
        assert state["escalation_level"] == "overdue"
        assert state["watchdog_status"] == "overdue"
        assert state["latest_outcome"]["deadline_exceeded"].startswith("2026-10-05")

        timeline = missions.timeline_for_mission("mission-escalation")
        kinds = [item["kind"] for item in timeline]
        assert "mission.escalation_critical" in kinds
        assert "mission.deadline_exceeded" in kinds

        missions.watchdog_for_mission(
            "mission-escalation",
            None,
            now="2026-10-05T12:02:00+00:00",
        )
        timeline_after = missions.timeline_for_mission("mission-escalation")
        assert kinds.count("mission.deadline_exceeded") == 1
        assert [item["kind"] for item in timeline_after].count("mission.deadline_exceeded") == 1
    finally:
        missions.close()


def test_escalation_policy_validation_and_control_snapshot(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        missions.create(
            "conversation-1",
            "Policy mission",
            "watch",
            mission_id="mission-escalation-policy",
        )
        try:
            missions.set_escalation_policy(
                "mission-escalation-policy",
                warning_before_seconds=60,
                critical_before_seconds=120,
            )
        except ValueError as exc:
            assert "warning_before_seconds" in str(exc)
        else:
            raise AssertionError("expected threshold ordering validation")

        state = missions.set_escalation_policy(
            "mission-escalation-policy",
            warning_before_seconds=600,
            critical_before_seconds=120,
        )
        assert state["escalation_warning_seconds"] == 600.0
        assert state["escalation_critical_seconds"] == 120.0

        missions.set_deadline(
            "mission-escalation-policy",
            "2099-01-01T00:00:00+00:00",
        )
        snapshot = missions.control_snapshot("mission-escalation-policy", tmp_path / "data" / "oth.db")
        assert snapshot["escalation"]["level"] == "normal"
        assert snapshot["escalation"]["warning_before_seconds"] == 600.0
        assert snapshot["escalation"]["critical_before_seconds"] == 120.0
    finally:
        missions.close()
