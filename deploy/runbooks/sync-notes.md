# Notes Sync Runbook

## Direction
Online ingestion node `<->` offline use node.

## Pull from remote
```bash
curl -X POST http://localhost:8000/sync/notes/pull \
  -H "Content-Type: application/json" \
  -d '{"since": null, "limit": 500}'
```

## Push to remote
```bash
curl -X POST http://localhost:8000/sync/notes/push \
  -H "Content-Type: application/json" \
  -d '{"source_node":"offline-node-1","notes":[]}'
```

## Conflict policy
- `sync_version` wins.
- If equal version, newer `updated_at` wins.
