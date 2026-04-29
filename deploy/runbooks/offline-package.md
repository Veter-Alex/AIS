# Offline Package Contract

## Purpose
Define a versioned offline package format for transferring data between ingestion and offline nodes.

## Package format
- Archive: `offline_bundle_<timestamp>.tar.gz`
- Required contents:
  - `db.dump` (PostgreSQL custom format, `pg_dump -Fc`)
  - `vessel_images/`
  - `manifest.json`
  - `checksums.sha256`

## Versioning rules
- `manifest.json.schema_version` is incremented on breaking DB changes.
- Alembic migration history is the source of truth for schema evolution.

## Export package
```bash
chmod +x deploy/offline/export_offline_bundle.sh
POSTGRES_USER=user POSTGRES_DB=vessels_db deploy/offline/export_offline_bundle.sh v1
```

## Restore package
```bash
chmod +x deploy/offline/restore_offline_bundle.sh
POSTGRES_USER=user POSTGRES_DB=vessels_db deploy/offline/restore_offline_bundle.sh backups/offline_bundle_*.tar.gz
```
