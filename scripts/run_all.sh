#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=${1:-config/portfolio.json}
PORT=${2:-8000}
if [ -z "${RUN_LIVE_PRODUCER+x}" ]; then
  RUN_LIVE_PRODUCER=1
  RUN_LIVE_PRODUCER_AUTO=1
else
  RUN_LIVE_PRODUCER_AUTO=0
fi
if [ -z "${RUN_WORKER+x}" ]; then
  RUN_WORKER=1
  RUN_WORKER_AUTO=1
else
  RUN_WORKER_AUTO=0
fi
DOCKER_DAEMON_OK=0

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    DOCKER_DAEMON_OK=1
    if [ -f docker-compose.yml ]; then
      docker compose up -d redpanda redis || true
    else
      docker compose -f docker-compose.kafka.yml up -d || true
    fi
  else
    echo "Docker is installed but daemon is not running."
  fi
else
  echo "Docker not found. Continuing without starting Redis/Kafka containers."
fi

if [ "${RUN_LIVE_PRODUCER_AUTO}" = "1" ] && [ "${DOCKER_DAEMON_OK}" != "1" ]; then
  echo "Disabling live producer because Docker/Kafka is not available."
  RUN_LIVE_PRODUCER=0
fi

export PORT
export STOCKS_CONFIG_PATH="${CONFIG_PATH}"

./scripts/run_migrations.sh "$CONFIG_PATH"
export RUN_MIGRATIONS_ON_BOOT=0

REDIS_OK=0
if python - "$CONFIG_PATH" <<'PY'
from pathlib import Path
import sys
from src.config import load_config
from src.queueing import redis_health

cfg = load_config(Path(sys.argv[1]))
raise SystemExit(0 if redis_health(cfg) else 1)
PY
then
  REDIS_OK=1
fi

if [ "${RUN_WORKER_AUTO}" = "1" ] && [ "${REDIS_OK}" != "1" ]; then
  echo "Disabling worker because Redis is not available."
  RUN_WORKER=0
fi

./scripts/run_web.sh &
WEB_PID=$!

WORKER_PID=""
if [ "${RUN_WORKER}" = "1" ]; then
  ./scripts/run_worker.sh "$CONFIG_PATH" &
  WORKER_PID=$!
fi

PRODUCER_PID=""
if [ "${RUN_LIVE_PRODUCER}" = "1" ]; then
  ./scripts/run_live_producer.sh "$CONFIG_PATH" &
  PRODUCER_PID=$!
fi

trap 'kill $WEB_PID ${WORKER_PID:-} ${PRODUCER_PID:-} 2>/dev/null || true' EXIT

sleep 2
if command -v open >/dev/null 2>&1; then
  open "http://127.0.0.1:${PORT}"
fi

WAIT_PIDS=("$WEB_PID")
if [ -n "${WORKER_PID}" ]; then
  WAIT_PIDS+=("$WORKER_PID")
fi
if [ -n "${PRODUCER_PID}" ]; then
  WAIT_PIDS+=("$PRODUCER_PID")
fi
wait "${WAIT_PIDS[@]}"
