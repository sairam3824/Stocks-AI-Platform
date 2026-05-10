from types import SimpleNamespace

import src.webapp as webapp


class _DummyThread:
    def __init__(self, alive: bool) -> None:
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive


def test_start_live_consumer_skips_when_thread_alive(monkeypatch) -> None:
    monkeypatch.setattr(
        webapp,
        "_load_runtime_config",
        lambda: SimpleNamespace(kafka_enabled=True, kafka_bootstrap_servers="x", kafka_topic="y"),
    )
    monkeypatch.setattr(webapp, "log_event", lambda *args, **kwargs: None)
    called = {"count": 0}

    def _start(*args, **kwargs):
        called["count"] += 1
        return _DummyThread(alive=True)

    monkeypatch.setattr(webapp, "start_consumer", _start)
    monkeypatch.setattr(webapp, "LIVE_CONSUMER_STARTED", True)
    monkeypatch.setattr(webapp, "LIVE_CONSUMER_THREAD", _DummyThread(alive=True))

    webapp._start_live_consumer()
    assert called["count"] == 0


def test_start_live_consumer_restarts_when_thread_dead(monkeypatch) -> None:
    monkeypatch.setattr(
        webapp,
        "_load_runtime_config",
        lambda: SimpleNamespace(kafka_enabled=True, kafka_bootstrap_servers="x", kafka_topic="y"),
    )
    monkeypatch.setattr(webapp, "log_event", lambda *args, **kwargs: None)
    called = {"count": 0}

    def _start(*args, **kwargs):
        called["count"] += 1
        return _DummyThread(alive=True)

    monkeypatch.setattr(webapp, "start_consumer", _start)
    monkeypatch.setattr(webapp, "LIVE_CONSUMER_STARTED", True)
    monkeypatch.setattr(webapp, "LIVE_CONSUMER_THREAD", _DummyThread(alive=False))

    webapp._start_live_consumer()
    assert called["count"] == 1
    assert webapp.LIVE_CONSUMER_THREAD is not None
    assert webapp.LIVE_CONSUMER_THREAD.is_alive()
