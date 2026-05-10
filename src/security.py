from __future__ import annotations

import secrets
import threading
import time
from collections import deque
from typing import Deque, Dict

from flask import Request


_RATE_LIMIT: Dict[str, Deque[float]] = {}
_RATE_LOCK = threading.Lock()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def allow_request(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    with _RATE_LOCK:
        bucket = _RATE_LIMIT.setdefault(key, deque())
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def get_or_create_csrf(session_obj) -> str:
    token = session_obj.get("csrf_token")
    if not token:
        token = secrets.token_hex(24)
        session_obj["csrf_token"] = token
    return token


def validate_csrf(request: Request, session_obj) -> bool:
    expected = session_obj.get("csrf_token", "")
    supplied = (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRF-Token", "")
    )
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))
