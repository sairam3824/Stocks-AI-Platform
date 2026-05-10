from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .queueing import get_forecast_queue, get_redis_connection


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RQ worker for forecast jobs")
    parser.add_argument("--config", default="config/portfolio.json")
    args = parser.parse_args()

    try:
        from rq import Worker
    except Exception as exc:  # pragma: no cover - runtime fallback
        print(f"[WARN] RQ worker not available ({exc}). Install dependencies with: pip install -r requirements.txt")
        return

    config = load_config(Path(args.config))
    connection = get_redis_connection(config)
    queue = get_forecast_queue(config)
    worker = Worker([queue.name], connection=connection)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
