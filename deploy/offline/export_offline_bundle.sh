#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-v1}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BUNDLE_DIR="backups/offline_bundle_${STAMP}"
mkdir -p "${BUNDLE_DIR}"

echo "Exporting PostgreSQL dump..."
docker compose -f deploy/compose/ingestion.yml exec -T db \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc \
  > "${BUNDLE_DIR}/db.dump"

echo "Copying images..."
mkdir -p "${BUNDLE_DIR}/vessel_images"
cp -r data/vessel_images/. "${BUNDLE_DIR}/vessel_images/" 2>/dev/null || true

cat > "${BUNDLE_DIR}/manifest.json" <<EOF
{
  "schema_version": "${VERSION}",
  "created_at": "$(date -Iseconds)",
  "postgres_db": "${POSTGRES_DB}",
  "files": ["db.dump", "vessel_images/"]
}
EOF

(
  cd "${BUNDLE_DIR}"
  sha256sum db.dump manifest.json > checksums.sha256
)

tar -czf "${BUNDLE_DIR}.tar.gz" -C backups "offline_bundle_${STAMP}"
echo "Created bundle: ${BUNDLE_DIR}.tar.gz"
