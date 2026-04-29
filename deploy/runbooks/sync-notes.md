# Notes Sync Runbook

## Purpose
Synchronize vessel notes between ingestion node and offline node.

## Node roles
- Ingestion node: primary online data source.
- Offline node: local consumer node that exchanges notes.

## Pull notes
```bash
curl -X POST http://localhost:8000/sync/notes/pull \
  -H "Content-Type: application/json" \
  -d '{"since": null, "limit": 500}'
```

## Push notes
```bash
curl -X POST http://localhost:8000/sync/notes/push \
  -H "Content-Type: application/json" \
  -d '{"source_node":"offline-node-1","notes":[]}'
```

## Conflict policy
- Higher `sync_version` wins.
- If `sync_version` is equal, newer `updated_at` wins.
