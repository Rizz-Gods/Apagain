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



def test_mission_tracks_spawned_child_tasks(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create("conversation-1", "Multi-stage mission", "echo -> verify", mission_id="mission-graph")
        task = kernel.submit(
            "demo",
            "echo",
            {
                "message": "stage-1",
                "mission_id": "mission-graph",
                "conversation_id": "conversation-1",
                "max_retries": 0,
                "next": [{"capability": "demo", "action": "echo", "payload": {"message": "stage-2"}}],
            },
            50,
        )
        missions.attach_root_tasks("mission-graph", [task.id])

        first = kernel.dispatch(task.id)
        assert first["status"] == "succeeded"
        assert len(first["spawned"]) == 1

        child_id = first["spawned"][0]
        child = kernel.db.get_task(child_id)
        child_payload = json.loads(child["payload"])
        assert child_payload["mission_id"] == "mission-graph"
        assert child_payload["conversation_id"] == "conversation-1"

        mid = missions.get("mission-graph")
        assert mid["status"] == "queued"
        graph = missions.graph_for_mission("mission-graph", tmp_path / "data" / "oth.db")
        assert graph["counts"]["total"] == 2
        assert graph["counts"]["queued"] == 1
        assert len(graph["edges"]) == 1

        kernel.db.update_task(child_id, "failed", "2026-10-05T00:00:00+00:00")
        missions.update_from_task(
            "mission-graph",
            child_id,
            "failed",
            {"error": "child transient failure"},
            task_db=kernel.db.path,
        )

        resumed = kernel.resume_mission("mission-graph", task_ids=[child_id])
        assert resumed["queued"] == [child_id]
        assert kernel.db.get_task(task.id)["status"] == "succeeded"
        assert kernel.db.get_task(child_id)["status"] == "queued"

        second = kernel.dispatch(child_id)
        assert second["status"] == "succeeded"
        final = missions.get("mission-graph")
        assert final["status"] == "succeeded"
        assert final["latest_task_id"] == child_id
        assert final["latest_outcome"]["spawned_tasks"] == []
    finally:
        kernel.close()
        missions.close()



def test_mission_reconcile_recovers_after_stale_task_failure(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create("conversation-1", "Recover mission", "resume safely", mission_id="mission-recover")
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "recover-me", "mission_id": "mission-recover", "max_retries": 0},
            50,
        )
        missions.attach_root_tasks("mission-recover", [task.id])
        kernel.db.update_task(task.id, "running", "2026-10-05T00:00:00+00:00")
        missions.update_from_task(
            "mission-recover",
            task.id,
            "running",
            {"summary": "worker lease active"},
            task_db=kernel.db.path,
        )

        reclaimed = kernel.db.reclaim_stale_tasks(
            "2099-01-01T00:00:00+00:00",
            "2098-01-01T00:00:00+00:00",
        )
        assert reclaimed == 1

        result = missions.reconcile(kernel.db.path)
        state = missions.get("mission-recover")
        assert result["changed"] == 1
        assert state["status"] == "failed"
        assert state["latest_task_id"] == task.id
        assert state["latest_outcome"]["reconciled"] is True
        assert state["latest_outcome"]["graph_status"] == "failed"
    finally:
        kernel.close()
        missions.close()


def test_failed_mission_can_resume_without_repeating_successful_work(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create("conversation-1", "Resume mission", "retry failed node", mission_id="mission-resume")
        task = kernel.submit(
            "demo",
            "echo",
            {"message": "resume-me", "mission_id": "mission-resume", "max_retries": 0},
            50,
        )
        missions.attach_root_tasks("mission-resume", [task.id])
        kernel.db.update_task(task.id, "failed", "2026-10-05T00:00:00+00:00")
        missions.update_from_task(
            "mission-resume",
            task.id,
            "failed",
            {"error": "transient failure"},
            task_db=kernel.db.path,
        )

        resumed = kernel.resume_mission("mission-resume")
        assert resumed["queued"] == [task.id]
        assert resumed["blocked"] == []
        assert resumed["status"] == "queued"

        stored = kernel.db.get_task(task.id)
        payload = json.loads(stored["payload"])
        assert stored["status"] == "queued"
        assert payload["_resume_count"] == 1
        assert payload["_failed_lane_workers"] == []

        result = kernel.dispatch(task.id)
        assert result["status"] == "succeeded"
        assert missions.get("mission-resume")["status"] == "succeeded"
    finally:
        kernel.close()
        missions.close()


def test_external_failed_mission_requires_explicit_resume_approval(tmp_path):
    write_minimal_config(tmp_path)
    (tmp_path / "config" / "workforce.json").write_text(
        '{"capabilities":{"social-actions":{"risk":"external"}}}',
        encoding="utf-8",
    )
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        assert kernel.workforce.capability_for("social-actions").risk == "external"
        missions.create("conversation-1", "External resume", "operator gated retry", mission_id="mission-external")
        task = kernel.submit(
            "social-actions",
            "publish_text",
            {
                "message": "retry",
                "mission_id": "mission-external",
                "max_retries": 0,
            },
            50,
        )
        missions.attach_root_tasks("mission-external", [task.id])
        kernel.db.update_task(task.id, "failed", "2026-10-05T00:00:00+00:00")
        missions.update_from_task(
            "mission-external",
            task.id,
            "failed",
            {"error": "publish failed"},
            task_db=kernel.db.path,
        )

        gated = kernel.resume_mission("mission-external")
        assert gated["queued"] == []
        assert gated["blocked"][0]["reason"] == "operator_approval_required"
        assert kernel.db.get_task(task.id)["status"] == "failed"

        approved = kernel.resume_mission("mission-external", approve_external=True)
        assert approved["queued"] == [task.id]
        stored = kernel.db.get_task(task.id)
        payload = json.loads(stored["payload"])
        assert stored["status"] == "queued"
        assert payload["approved"] is True
        assert payload["approved_by"] == "operator"
    finally:
        kernel.close()
        missions.close()


def test_policy_block_is_persisted_and_mission_approval_requeues_task(tmp_path):
    write_minimal_config(tmp_path)
    missions = MissionStateStore(tmp_path / "data" / "console.db")
    kernel = OTHKernel(tmp_path)
    try:
        missions.create(
            "conversation-1",
            "Approval mission",
            "external action approval",
            mission_id="mission-approval",
        )
        task = kernel.submit(
            "social-actions",
            "publish_text",
            {
                "text": "approval-test",
                "mission_id": "mission-approval",
                "conversation_id": "conversation-1",
                "max_retries": 0,
            },
            80,
        )
        missions.attach_root_tasks("mission-approval", [task.id])

        result = kernel.dispatch(task.id)
        assert result["status"] == "blocked"
        state = missions.get("mission-approval")
        assert state["status"] == "blocked"
        assert state["latest_outcome"]["approval_required"] is True

        approved = kernel.approve_mission("mission-approval")
        assert approved["approved"] == [task.id]
        assert approved["status"] == "queued"
        assert kernel.db.get_task(task.id)["status"] == "queued"
        refreshed = missions.get("mission-approval")
        assert refreshed["status"] == "queued"
        assert refreshed["latest_outcome"]["approval_granted"] is True
    finally:
        kernel.close()
        missions.close()
