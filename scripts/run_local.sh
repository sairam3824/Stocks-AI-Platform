#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=${1:-config/portfolio.json}
PORT=${2:-8000}

python -m src.run_local --config "$CONFIG_PATH" --port "$PORT"
