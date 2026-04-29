# Offline Use Runbook

## Purpose
Run the offline node to use already accumulated data without internet access.

## Node role
- Offline node: browse, search, filter, edit, and manage notes.

## Stack
- `db`
- `vessel_api`
- `vessel_frontend`

Compose profile: `deploy/compose/use-offline.yml`

## Start
```bash
make up-offline
```

## Verify
- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`

## Stop
```bash
make down-offline
```
