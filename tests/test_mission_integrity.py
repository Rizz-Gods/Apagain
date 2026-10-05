from pathlib import Path
import json

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


def test_healthy_mission_passes_integrity(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("c1", "integrity", "healthy", mission_id="mission-integrity")
        report = store.check_integrity("mission-integrity", kernel.db.path)
        assert report["status"] == "healthy"
        assert report["violations"] == []
        assert report["audit_integrity"]["valid"] is True
    finally:
        kernel.close()
        store.close()


def test_integrity_detects_terminal_mission_with_active_task(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("c1", "integrity", "active mismatch", mission_id="mission-integrity")
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "active", "mission_id": "mission-integrity"},
            50,
        )
        store.attach_root_tasks("mission-integrity", [task.id])
        kernel.db.update_task(task.id, "running", "2026-10-05T12:00:00+00:00")
        store.db.execute(
            "UPDATE missions SET status='succeeded', completed_at='2026-10-05T12:01:00+00:00' WHERE id=?",
            ("mission-integrity",),
        )
        store.db.commit()

        report = store.check_integrity("mission-integrity", kernel.db.path)
        codes = {item["code"] for item in report["violations"]}
        assert report["status"] == "violated"
        assert "terminal_with_active_tasks" in codes
        assert "mission_status_mismatch" in codes
        attention = store.attention_for_mission("mission-integrity")
        assert any(item["kind"] == "mission.integrity_violation" for item in attention)
    finally:
        kernel.close()
        store.close()


def test_integrity_detects_policy_hash_mismatch(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("c1", "integrity", "policy mismatch", mission_id="mission-policy")
        store.db.execute(
            "UPDATE missions SET policy_hash='tampered' WHERE id=?",
            ("mission-policy",),
        )
        store.db.commit()
        report = store.check_integrity("mission-policy", kernel.db.path)
        assert any(item["code"] == "policy_hash_mismatch" for item in report["violations"])
    finally:
        kernel.close()
        store.close()


def test_integrity_deduplicates_same_violation_fingerprint(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("c1", "integrity", "dedupe", mission_id="mission-integrity")
        store.db.execute(
            "UPDATE missions SET policy_hash='tampered' WHERE id=?",
            ("mission-integrity",),
        )
        store.db.commit()
        first = store.check_integrity("mission-integrity", kernel.db.path)
        second = store.check_integrity("mission-integrity", kernel.db.path)
        assert first["fingerprint"] == second["fingerprint"]
        timeline = store.timeline_for_mission("mission-integrity")
        assert sum(item["kind"] == "mission.integrity_violation" for item in timeline) == 1
    finally:
        kernel.close()
        store.close()


def test_integrity_history_and_control_exposure(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("c1", "integrity", "history", mission_id="mission-integrity")
        store.check_integrity("mission-integrity", kernel.db.path)
        snapshot = store.control_snapshot("mission-integrity", kernel.db.path)
        history = store.integrity_history("mission-integrity")
        assert snapshot["integrity"]["status"] == "healthy"
        assert history[-1]["status"] == "healthy"
        assert history[-1]["fingerprint"] == snapshot["integrity"]["fingerprint"]
    finally:
        kernel.close()
        store.close()
