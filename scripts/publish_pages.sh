#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=${1:-config/portfolio.json}
python -m src.publish --config "$CONFIG_PATH"
