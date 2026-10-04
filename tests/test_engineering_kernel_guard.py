from pathlib import Path
from types import SimpleNamespace

from oth.core.kernel import OTHKernel
from oth.workers.builtin import WorkerResult


class EngineeringEvidenceWorker:
    def __init__(self, worker_id, changed):
        self.id = worker_id
        self.changed = changed

    def supports(self, capability):
        return capability == "engineering"

    def execute(self, action, payload):
        return WorkerResult(
            True,
            {
                "worker": self.id,
                "implementation_expected": True,
                "implementation_changed": self.changed,
            },
        )


def test_kernel_rejects_false_positive_engineering_success(tmp_path):
    root = Path(tmp_path)
    (root / "config").mkdir()
    (root / "data").mkdir()
    (root / "config" / "agents.json").write_text('{"agents":[]}', encoding="utf-8")
    (root / "config" / "skills.json").write_text('{"skills":[]}', encoding="utf-8")
    (root / "config" / "policies.json").write_text(
        '{"external_actions_require_approval":true,"financial_actions_require_approval":true}',
        encoding="utf-8",
    )
    (root / "config" / "tools.json").write_text('{"tools":[]}', encoding="utf-8")

    kernel = OTHKernel(root)
    kernel.workforce.workers = {
        "fake-first": {
            "id": "fake-first",
            "name": "fake-first",
            "capabilities": ["engineering"],
            "status": "available",
            "metadata": {"priority": 100},
        },
        "fake-second": {
            "id": "fake-second",
            "name": "fake-second",
            "capabilities": ["engineering"],
            "status": "available",
            "metadata": {"priority": 90},
        },
    }
    kernel.workforce.capability_for = lambda capability: SimpleNamespace(
        risk="safe",
        required_permissions=(),
    )
    kernel.workforce.contract_for = lambda worker_id: SimpleNamespace(
        capability_grants={"engineering": ()},
        permissions=(),
        retry=SimpleNamespace(max_attempts=0),
    )
    kernel.lanes.config = {"max_lanes": 2, "fallbacks": {}}
    kernel.workers = [
        EngineeringEvidenceWorker("fake-first", changed=False),
        EngineeringEvidenceWorker("fake-second", changed=True),
    ]

    task = kernel.submit("engineering", "execute", {"prompt": "Implement a change"})
    result = kernel.dispatch(task.id)

    assert result["status"] == "succeeded"
    assert result["worker"] == "fake-second"
    events = kernel.db.conn.execute(
        "SELECT kind FROM events WHERE task_id=? ORDER BY id", (task.id,)
    ).fetchall()
    kinds = [row["kind"] for row in events]
    assert "lane.1.failed" in kinds
    assert "lane.2.succeeded" in kinds
    kernel.close()
