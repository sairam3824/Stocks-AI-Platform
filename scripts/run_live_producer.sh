#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH=${1:-config/portfolio.json}

python -m src.live_producer --config "$CONFIG_PATH"
