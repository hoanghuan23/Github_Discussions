import importlib

import app.core.config as config


def test_scheduler_interval_seconds_defaults_to_60(monkeypatch):
    monkeypatch.delenv("SCHEDULER_INTERVAL_SECONDS", raising=False)

    reloaded = importlib.reload(config)

    assert reloaded.Settings().scheduler_interval_seconds == 60


def test_scheduler_interval_seconds_reads_env(monkeypatch):
    monkeypatch.setenv("SCHEDULER_INTERVAL_SECONDS", "15")

    reloaded = importlib.reload(config)

    assert reloaded.Settings().scheduler_interval_seconds == 15
    monkeypatch.delenv("SCHEDULER_INTERVAL_SECONDS", raising=False)
    importlib.reload(config)
