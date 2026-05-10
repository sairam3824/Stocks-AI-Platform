from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Dict


_COUNTERS: Dict[str, float] = {}
_LOCK = threading.Lock()


def _logger() -> logging.Logger:
    logger = logging.getLogger("stocks_ai")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(event: str, **fields) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "service": "stocks-ai",
        "env": os.environ.get("APP_ENV", "dev"),
    }
    payload.update(fields)
    _logger().info(json.dumps(payload, separators=(",", ":")))


def increment_counter(name: str, delta: float = 1.0) -> None:
    with _LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0.0) + float(delta)


def get_counters() -> Dict[str, float]:
    with _LOCK:
        return dict(_COUNTERS)
