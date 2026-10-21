#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export BACKEND_HOST_PORT="${BACKEND_HOST_PORT:-18880}"
export FRONTEND_HOST_PORT="${FRONTEND_HOST_PORT:-18888}"
compose=(docker compose -p shortcut-v3 -f docker-compose.yml -f docker-compose.v3.yml)
case "${1:-up}" in
  up) "${compose[@]}" up -d --build ;;
  down) "${compose[@]}" down ;;
  logs) "${compose[@]}" logs --tail=100 -f ;;
  config) "${compose[@]}" config --quiet ;;
  *) echo "Usage: bash scripts/v3.sh [up|down|logs|config]" >&2; exit 2 ;;
esac
