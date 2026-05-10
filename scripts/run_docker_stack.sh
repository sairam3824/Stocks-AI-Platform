#!/usr/bin/env bash
set -euo pipefail

docker compose up -d --build
echo "Stack is running:"
echo "  App (direct): http://127.0.0.1:8000"
echo "  App (nginx):  http://127.0.0.1:8080"
echo "  Redis:        redis://127.0.0.1:6379/0"
