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


def test_audit_chain_records_operator_mutations(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        store.create("conversation-1", "Audit mission", "record decisions", mission_id="mission-audit")
        store.set_deadline("mission-audit", "2030-01-01T00:00:00+00:00")
        store.set_escalation_policy("mission-audit", 900, 300)

        items = store.audit_for_mission("mission-audit")
        assert [item["action"] for item in items[:3]] == [
            "mission.created",
            "mission.deadline.set",
            "mission.escalation.policy_set",
        ]
        assert all(item["entry_hash"] for item in items)
        assert store.verify_audit_chain("mission-audit") == {
            "valid": True,
            "checked": len(items),
        }
    finally:
        store.close()


def test_audit_hash_tampering_is_detected(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        store.create("conversation-1", "Audit mission", "tamper test", mission_id="mission-audit")
        store.add_audit_event("mission-audit", "test.mutation", payload={"value": 1})

        before = store.verify_audit_chain()
        assert before["valid"] is True

        store.db.execute(
            "UPDATE mission_audit SET payload=? WHERE action='test.mutation'",
            ('{"value":999}',),
        )
        store.db.commit()

        after = store.verify_audit_chain()
        assert after["valid"] is False
        assert after["reason"] == "hash_chain_mismatch"
    finally:
        store.close()


def test_attention_acknowledgement_is_audited(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        store.create("conversation-1", "Attention mission", "ack", mission_id="mission-attention")
        store.add_timeline_event(
            "mission-attention",
            "mission.escalation_critical",
            {"seconds_to_deadline": 30},
            status="queued",
        )
        attention = store.list_attention(mission_id="mission-attention")[0]
        result = store.acknowledge_attention(attention["id"], "operator")
        assert result["status"] == "acknowledged"

        actions = [item["action"] for item in store.audit_for_mission("mission-attention")]
        assert "attention.acknowledge" in actions
    finally:
        store.close()


def test_control_snapshot_exposes_audit_integrity(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("conversation-1", "Control audit", "snapshot", mission_id="mission-control-audit")
        snapshot = store.control_snapshot("mission-control-audit", kernel.db.path)
        assert snapshot["audit"]
        assert snapshot["audit_integrity"]["valid"] is True
        assert snapshot["audit"][-1]["action"] == "mission.created"
    finally:
        kernel.close()
        store.close()


def test_approval_is_recorded_as_operator_audit(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("conversation-1", "Approval audit", "operator gate", mission_id="mission-approval-audit")
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "blocked", "mission_id": "mission-approval-audit"},
            50,
        )
        store.attach_root_tasks("mission-approval-audit", [task.id])
        kernel.db.update_task(task.id, "blocked", "2026-10-05T10:00:00+00:00")
        store.update_from_task(
            "mission-approval-audit",
            task.id,
            "blocked",
            {"error": "operator approval required", "approval_required": True},
            task_db=kernel.db.path,
        )

        result = kernel.approve_mission("mission-approval-audit")
        assert result["approved"] == [task.id]

        audit = store.audit_for_mission("mission-approval-audit")
        approvals = [item for item in audit if item["action"] == "task.approve"]
        assert len(approvals) == 1
        assert approvals[0]["actor"] == "operator"
        assert approvals[0]["task_id"] == task.id
        assert store.verify_audit_chain("mission-approval-audit")["valid"] is True
    finally:
        kernel.close()
        store.close()
