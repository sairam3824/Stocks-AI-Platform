#!/usr/bin/env bash
set -euo pipefail

PORT=${PORT:-8000}
WEB_CONCURRENCY=${WEB_CONCURRENCY:-2}
WEB_THREADS=${WEB_THREADS:-4}
WEB_TIMEOUT=${WEB_TIMEOUT:-180}
CONFIG_PATH=${STOCKS_CONFIG_PATH:-config/portfolio.json}

if [ "${RUN_MIGRATIONS_ON_BOOT:-1}" = "1" ]; then
  STOCKS_CONFIG_PATH="${CONFIG_PATH}" python -m alembic upgrade head
fi

if python -c "import gunicorn" >/dev/null 2>&1; then
  exec python -m gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WEB_CONCURRENCY}" \
    --threads "${WEB_THREADS}" \
    --timeout "${WEB_TIMEOUT}" \
    src.webapp:app
fi

echo "[WARN] gunicorn is not installed. Falling back to Flask development server."
exec python -m src.webapp
