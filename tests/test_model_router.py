from oth.core.model_router import ModelRouter


def test_model_router_scores_light_and_complex_tasks(tmp_path):
    router = ModelRouter(tmp_path)
    light = router.complexity("rename a variable and run tests")
    complex_task = router.complexity(
        "architect and implement a distributed authentication migration with database changes, "
        "concurrency safeguards, browser integration, and performance debugging"
    )
    assert 0 <= light < complex_task <= 1


def test_model_router_uses_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OTH_OPENCODE_MODEL", "ollama/custom-model")
    route = ModelRouter(tmp_path).route("build a feature")
    assert route.tier == "override"
    assert route.model == "ollama/custom-model"


def test_model_router_local_fallback_when_no_frontier(tmp_path):
    router = ModelRouter(tmp_path)
    route = router.route("build a simple utility")
    assert route.model.startswith("ollama/")
    assert route.tier in {"local", "standard"}
