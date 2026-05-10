from src.security import allow_request


def test_rate_limit_blocks_after_limit() -> None:
    key = "unit-test-key"
    assert allow_request(key, limit=2, window_seconds=60) is True
    assert allow_request(key, limit=2, window_seconds=60) is True
    assert allow_request(key, limit=2, window_seconds=60) is False
