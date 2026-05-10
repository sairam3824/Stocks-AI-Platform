#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=${1:-config/portfolio.json}

if [ "${RUN_MIGRATIONS_ON_BOOT:-1}" = "1" ]; then
  STOCKS_CONFIG_PATH="${CONFIG_PATH}" python -m alembic upgrade head
fi

if ! python -c "import rq" >/dev/null 2>&1; then
  echo "[WARN] rq package not installed. Worker will not run. Install with: pip install -r requirements.txt"
  exit 0
fi

# Avoid noisy tracebacks when Redis is intentionally unavailable in local runs.
if ! python - "$CONFIG_PATH" <<'PY'
from pathlib import Path
import sys
from src.config import load_config
from src.queueing import redis_health

cfg = load_config(Path(sys.argv[1]))
raise SystemExit(0 if redis_health(cfg) else 1)
PY
then
  echo "[WARN] Redis is unavailable. Worker will not start."
  exit 0
fi

exec python -m src.worker --config "${CONFIG_PATH}"
