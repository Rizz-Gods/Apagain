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


def test_mission_creation_pins_policy_revision(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        mission = store.create("c1", "governance", "pin policy", mission_id="mission-policy")
        current = store.policy_for_mission("mission-policy")
        assert mission["policy_revision"] == 1
        assert current["revision"] == 1
        assert current["policy"]["approval"]["external_actions_require_approval"] is True
        assert current["policy"]["budget"]["max_tasks"] == 256
        assert current["policy"]["cancellation"]["mode"] == "graceful"
        assert len(store.policy_revisions_for_mission("mission-policy")) == 1
    finally:
        store.close()


def test_policy_mutation_creates_immutable_revision(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        store.create("c1", "governance", "mutate", mission_id="mission-policy")
        before = store.policy_for_mission("mission-policy")
        after = store.set_policy(
            "mission-policy",
            external_actions_require_approval=False,
            actor="operator",
            reason="allow controlled external work",
        )
        assert after["revision"] == before["revision"] + 1
        assert after["policy"]["approval"]["external_actions_require_approval"] is False
        revisions = store.policy_revisions_for_mission("mission-policy")
        assert len(revisions) == 2
        assert revisions[0]["revision"] == 1
        assert revisions[0]["policy"]["approval"]["external_actions_require_approval"] is True
        assert revisions[1]["revision"] == 2
        assert revisions[1]["policy"]["approval"]["external_actions_require_approval"] is False
        assert revisions[0]["hash"] != revisions[1]["hash"]
    finally:
        store.close()


def test_budget_deadline_and_escalation_changes_pin_revisions(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("c1", "governance", "mutations", mission_id="mission-policy")
        store.set_budget("mission-policy", max_tasks=4, max_retries=2, task_db=kernel.db.path)
        store.set_escalation_policy("mission-policy", 900, 300)
        store.set_deadline("mission-policy", "2030-01-01T00:00:00+00:00", now="2026-10-05T12:00:00+00:00")
        current = store.policy_for_mission("mission-policy")
        assert current["revision"] == 4
        assert current["policy"]["budget"] == {"max_tasks": 4, "max_retries": 2}
        assert current["policy"]["escalation"]["warning_before_seconds"] == 900.0
        assert current["policy"]["deadline"]["deadline_at"].startswith("2030-01-01")
    finally:
        kernel.close()
        store.close()


def test_kernel_uses_pinned_mission_policy_and_records_revision(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("c1", "governance", "enforce", mission_id="mission-policy")
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "external", "risk": "external", "mission_id": "mission-policy"},
            50,
        )
        store.attach_root_tasks("mission-policy", [task.id])

        first = kernel.dispatch(task.id)
        assert first["status"] == "blocked"

        store.set_policy(
            "mission-policy",
            external_actions_require_approval=False,
            actor="operator",
            reason="controlled exception",
        )
        task2 = kernel.submit(
            "demo",
            "echo",
            {"message": "external-allowed", "risk": "external", "mission_id": "mission-policy"},
            50,
        )
        result = kernel.dispatch(task2.id)
        assert result["status"] == "succeeded"

        policy_events = [
            row
            for row in kernel.db.conn.execute(
                "SELECT payload FROM events WHERE kind='task.policy_evaluated' ORDER BY rowid"
            ).fetchall()
        ]
        assert len(policy_events) >= 2
        assert '"policy_revision": 1' in policy_events[-2][0]
        assert '"decision": "blocked"' in policy_events[-2][0]
        assert '"policy_revision": 2' in policy_events[-1][0]
        assert '"decision": "allowed"' in policy_events[-1][0]
    finally:
        kernel.close()
        store.close()


def test_operator_audit_carries_active_policy_revision(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    try:
        store.create("c1", "governance", "audit evidence", mission_id="mission-policy")
        store.add_audit_event(
            "mission-policy",
            "test.operator_action",
            actor="operator",
            payload={"decision": "test"},
        )
        store.set_policy(
            "mission-policy",
            external_actions_require_approval=False,
            reason="controlled change",
        )
        items = store.audit_for_mission("mission-policy")
        test_item = next(item for item in items if item["action"] == "test.operator_action")
        policy_change = next(item for item in items if item["action"] == "mission.policy.changed")
        assert test_item["payload"]["policy_revision"] == 1
        assert policy_change["payload"]["policy_revision"] == 2
        assert policy_change["payload"]["revision"] == 2
    finally:
        store.close()


def test_replay_exposes_policy_revisions(tmp_path):
    write_minimal_config(tmp_path)
    store = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        store.create("c1", "governance", "replay", mission_id="mission-policy")
        store.set_policy("mission-policy", external_actions_require_approval=False)
        replay = store.replay_for_mission("mission-policy", kernel.db.path)
        assert replay["policy_revision_count"] == 2
        assert replay["policy"]["revision"] == 2
        assert any(item["source"] == "policy" for item in replay["replay"])
    finally:
        kernel.close()
        store.close()
