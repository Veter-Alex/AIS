# Offline Data Package Contract

## Bundle format
- Archive: `offline_bundle_<timestamp>.tar.gz`
- Required files:
  - `db.dump` (PostgreSQL custom format, `pg_dump -Fc`)
  - `vessel_images/`
  - `manifest.json`
  - `checksums.sha256`

## Schema/version contract
- `manifest.json.schema_version` must be incremented on breaking DB changes.
- Alembic migration changelog is source of truth for schema updates.

## Export
```bash
chmod +x deploy/offline/export_offline_bundle.sh
POSTGRES_USER=user POSTGRES_DB=vessels_db deploy/offline/export_offline_bundle.sh v1
```

## Restore
```bash
chmod +x deploy/offline/restore_offline_bundle.sh
POSTGRES_USER=user POSTGRES_DB=vessels_db deploy/offline/restore_offline_bundle.sh backups/offline_bundle_*.tar.gz
```
