from pathlib import Path
from subprocess import CompletedProcess

from oth.core.engineering import EngineeringWorker
from oth.core.engineering_fallback import EngineeringFallback
from oth.core.pilot import PilotPlanner


def test_pilot_routes_build_mission_to_engineering():
    plan = PilotPlanner().plan("Build the unlimited-context layer for OTH")
    assert plan.tasks[0].capability == "engineering"
    assert plan.tasks[0].action == "execute"
    assert plan.tasks[0].priority == 95


def test_engineering_worker_reports_provider_unavailable(tmp_path):
    worker = EngineeringWorker(tmp_path)
    worker._opencode = lambda: None
    result = worker.execute("execute", {"prompt": "modify the repo"})
    assert not result.success
    assert result.error.startswith("provider_unavailable")


def test_engineering_worker_runs_verification(monkeypatch, tmp_path):
    worker = EngineeringWorker(tmp_path)
    worker._opencode = lambda: "opencode"
    worker._test_command = lambda: ["pytest", "-q"]

    calls = []

    def fake_run(command, timeout):
        calls.append(command)
        if command[:2] == ["git", "status"]:
            return CompletedProcess(command, 0, "", "")
        if command[0] == "opencode":
            return CompletedProcess(command, 0, '{"type":"text","text":"implemented"}', "")
        return CompletedProcess(command, 0, "2 passed", "")

    monkeypatch.setattr(worker, "_run", fake_run)
    result = worker.execute("execute", {"prompt": "implement a safe change"})
    assert result.success
    assert result.output["verification"]["passed"]
    assert any(command[0] == "opencode" for command in calls)


def test_engineering_fallback_never_claims_execution(tmp_path):
    worker = EngineeringFallback(tmp_path)
    result = worker.execute("execute", {"prompt": "change code"})
    assert not result.success
    assert result.error == "engineering_provider_unavailable"
    assert result.output["claim"].startswith("No code was changed")
