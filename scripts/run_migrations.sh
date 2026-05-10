#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=${1:-config/portfolio.json}
export STOCKS_CONFIG_PATH="${CONFIG_PATH}"

exec python -m alembic upgrade head
