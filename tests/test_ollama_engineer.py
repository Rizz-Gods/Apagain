import json

import pytest

from oth.core.model_router import ModelRoute
from oth.core.ollama_engineer import NativeOllamaEngineer


def test_native_ollama_engineer_executes_file_edit(monkeypatch, tmp_path):
    worker = NativeOllamaEngineer(tmp_path)
    monkeypatch.setattr(worker, "_base_url", lambda: "http://127.0.0.1:1/v1")
    monkeypatch.setattr(worker.router, "route", lambda task: ModelRoute("local", "ollama/qwen2.5-coder:0.5b-instruct-q5_1", 0.2, "test"))

    responses = iter([
        {"choices": [{"message": {"content": json.dumps({
            "name": "write_file",
            "arguments": {"path": "hello.txt", "content": "hello from OTH"}
        })}}]},
        {"choices": [{"message": {"content": json.dumps({
            "name": "finish",
            "arguments": {"summary": "wrote hello.txt"}
        })}}]},
    ])
    monkeypatch.setattr(worker, "_chat", lambda *args, **kwargs: next(responses))
    result = worker.execute("execute", {"prompt": "Create hello.txt containing hello from OTH"})
    assert result.success
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello from OTH"
    assert result.output["provider"] == "ollama-native"
    assert result.output["tool_trace"][0]["tool"] == "write_file"


def test_native_ollama_engineer_replace_text(monkeypatch, tmp_path):
    (tmp_path / "sample.txt").write_text("alpha beta", encoding="utf-8")
    worker = NativeOllamaEngineer(tmp_path)
    monkeypatch.setattr(worker, "_base_url", lambda: "http://127.0.0.1:1/v1")
    monkeypatch.setattr(worker.router, "route", lambda task: ModelRoute("local", "ollama/qwen2.5-coder:0.5b-instruct-q5_1", 0.2, "test"))
    responses = iter([
        {"choices": [{"message": {"content": json.dumps({
            "name": "replace_text",
            "arguments": {"path": "sample.txt", "old_text": "alpha", "new_text": "gamma"}
        })}}]},
        {"choices": [{"message": {"content": json.dumps({
            "name": "finish",
            "arguments": {"summary": "updated sample"}
        })}}]},
    ])
    monkeypatch.setattr(worker, "_chat", lambda *args, **kwargs: next(responses))
    result = worker.execute("execute", {"prompt": "Replace alpha with gamma"})
    assert result.success
    assert (tmp_path / "sample.txt").read_text(encoding="utf-8") == "gamma beta"


def test_native_ollama_engineer_blocks_unsafe_commands(tmp_path):
    worker = NativeOllamaEngineer(tmp_path)
    with pytest.raises(ValueError):
        worker._run("powershell Get-Process")


def test_native_ollama_engineer_parser_handles_plain_json():
    parsed = NativeOllamaEngineer._parse_text_tool(
        '{"name":"list_files","arguments":{"path":"."}}'
    )
    assert parsed == ("list_files", {"path": "."})
