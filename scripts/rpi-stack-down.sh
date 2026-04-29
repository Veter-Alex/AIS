#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/AIS}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/compose/ingestion.yml}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"

cd "$PROJECT_DIR"
/usr/bin/docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down
