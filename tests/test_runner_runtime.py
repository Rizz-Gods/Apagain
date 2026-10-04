import oth.core.runner as runner_module
from oth.core.runner import OTHRunner


def test_runner_forever_keeps_the_loop_alive(monkeypatch):
    runner = object.__new__(OTHRunner)
    runner.running = True
    calls = {"runs": 0, "sleeps": 0}

    def fake_run_once():
        calls["runs"] += 1
        if calls["runs"] >= 2:
            runner.running = False
        return None

    def fake_sleep(interval):
        calls["sleeps"] += 1
        assert interval == 7

    runner.run_once = fake_run_once
    monkeypatch.setattr(runner_module.time, "sleep", fake_sleep)
    runner.interval = 7
    runner.run_forever()

    assert calls == {"runs": 2, "sleeps": 1}
