#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/AIS}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/compose/ingestion.yml}"

cd "$PROJECT_DIR"
/usr/bin/docker compose -f "$COMPOSE_FILE" up -d
