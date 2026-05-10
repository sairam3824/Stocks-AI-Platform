from __future__ import annotations

from redis import Redis

try:
    from rq import Queue
except Exception:  # pragma: no cover - optional dependency in fallback mode
    Queue = None

from .config import PortfolioConfig


def get_redis_connection(config: PortfolioConfig) -> Redis:
    return Redis.from_url(config.redis_url)


def get_forecast_queue(config: PortfolioConfig) -> Queue:
    if Queue is None:
        raise RuntimeError("rq package is not installed")
    connection = get_redis_connection(config)
    return Queue(config.rq_queue_name, connection=connection)


def redis_health(config: PortfolioConfig) -> bool:
    try:
        conn = get_redis_connection(config)
        return bool(conn.ping())
    except Exception:
        return False


def queue_depth(config: PortfolioConfig) -> int:
    try:
        if Queue is None:
            return -1
        queue = get_forecast_queue(config)
        return int(queue.count)
    except Exception:
        return -1
