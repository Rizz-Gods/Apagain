import json

from oth.core.engineering_evidence import (
    engineering_result_valid,
    implementation_expected,
    workspace_changed,
    workspace_fingerprint,
)
from oth.core.model_router import ModelRoute
from oth.core.db import Database
from oth.core.ollama_engineer import NativeOllamaEngineer


def _worker(tmp_path, monkeypatch, responses):
    worker = NativeOllamaEngineer(tmp_path)
    monkeypatch.setattr(worker, "_base_url", lambda: "http://127.0.0.1:1/v1")
    monkeypatch.setattr(
        worker.router,
        "route",
        lambda task: ModelRoute(
            "local",
            "ollama/qwen2.5-coder:0.5b-instruct-q5_1",
            0.2,
            "test",
        ),
    )
    iterator = iter(responses)
    monkeypatch.setattr(worker, "_chat", lambda *args, **kwargs: next(iterator))
    return worker


def test_implementation_expected_distinguishes_mutation_and_read_only():
    assert implementation_expected("execute", "Implement a new parser")
    assert not implementation_expected("execute", "Inspect the current parser")
    assert not implementation_expected("execute", "Inspect the current parser", {"read_only": True})


def test_workspace_fingerprint_detects_untracked_content(tmp_path):
    before = workspace_fingerprint(tmp_path)
    (tmp_path / "new.txt").write_text("one", encoding="utf-8")
    after = workspace_fingerprint(tmp_path)
    assert workspace_changed(before, after)


def test_native_worker_rejects_failed_tool_even_when_tests_pass(monkeypatch, tmp_path):
    worker = _worker(tmp_path, monkeypatch, [
        {"choices": [{"message": {"content": json.dumps({
            "name": "read_file",
            "arguments": {"path": "missing.txt"}
        })}}]},
        {"choices": [{"message": {"content": json.dumps({
            "name": "finish",
            "arguments": {"summary": "nothing changed"}
        })}}]},
    ])
    result = worker.execute("execute", {"prompt": "Implement the requested change"})
    assert not result.success
    assert result.output["implementation_expected"] is True
    assert result.error == "engineering_verification_failed"


def test_native_worker_rejects_finish_without_implementation_change(monkeypatch, tmp_path):
    worker = _worker(tmp_path, monkeypatch, [
        {"choices": [{"message": {"content": json.dumps({
            "name": "finish",
            "arguments": {"summary": "done"}
        })}}]},
    ])
    result = worker.execute("execute", {"prompt": "Implement the requested change"})
    assert not result.success
    assert result.output["implementation_changed"] is False


def test_engineering_result_contract_rejects_false_positive():
    assert not engineering_result_valid(
        "execute",
        {"implementation_expected": True, "implementation_changed": False},
        True,
    )
    assert engineering_result_valid(
        "execute",
        {"implementation_expected": False, "implementation_changed": False},
        True,
    )
    assert engineering_result_valid(
        "execute",
        {"implementation_expected": True, "implementation_changed": True},
        True,
    )


def test_engineering_scorecard_aggregates_worker_evaluations(tmp_path):
    db = Database(tmp_path / "oth.db")
    db.record_agent_result("ollama-engineer", True, None, "2026-01-01T00:00:00+00:00")
    db.record_agent_result("ollama-engineer", False, "failed", "2026-01-02T00:00:00+00:00")
    db.record_agent_result("opencode-engineer", False, "failed", "2026-01-03T00:00:00+00:00")
    db.record_evaluation("task-1", "engineering", "ollama-engineer", 1.0, True, 1, {}, "ok", "2026-01-01T00:00:00+00:00")
    db.record_evaluation("task-2", "engineering", "ollama-engineer", 0.0, False, 2, {}, "failed", "2026-01-02T00:00:00+00:00")
    db.record_evaluation("task-3", "engineering", "opencode-engineer", 0.5, False, 1, {}, "failed", "2026-01-03T00:00:00+00:00")
    rows = [dict(row) for row in db.engineering_scorecard()]
    by_worker = {row["worker_id"]: row for row in rows}
    assert by_worker["ollama-engineer"]["runs"] == 2
    assert by_worker["ollama-engineer"]["successes"] == 1
    assert by_worker["ollama-engineer"]["failures"] == 1
    assert by_worker["ollama-engineer"]["avg_quality"] == 0.5
