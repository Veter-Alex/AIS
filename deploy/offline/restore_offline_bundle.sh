#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <bundle.tar.gz>"
  exit 1
fi

BUNDLE="$1"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

tar -xzf "${BUNDLE}" -C "${TMP_DIR}"
INNER_DIR="$(find "${TMP_DIR}" -maxdepth 1 -type d -name "offline_bundle_*" | head -n 1)"

if [[ -z "${INNER_DIR}" ]]; then
  echo "Bundle structure is invalid."
  exit 1
fi

echo "Verifying checksums..."
(
  cd "${INNER_DIR}"
  sha256sum -c checksums.sha256
)

echo "Starting offline stack..."
docker compose -f deploy/compose/use-offline.yml up -d db

echo "Restoring PostgreSQL dump..."
cat "${INNER_DIR}/db.dump" | docker compose -f deploy/compose/use-offline.yml exec -T db \
  pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists --no-owner --no-privileges

echo "Restoring vessel images..."
mkdir -p data/vessel_images
cp -r "${INNER_DIR}/vessel_images/." data/vessel_images/ 2>/dev/null || true

echo "Offline bundle restored successfully."
