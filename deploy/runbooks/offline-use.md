# Offline Use Mode Runbook

## Purpose
Use accumulated database without internet: browse, search, filter, edit, notes.

## Stack
- `db`
- `vessel_api`
- `vessel_frontend`

Compose file: `deploy/compose/use-offline.yml`

## Start
```bash
make up-offline
```

## Access
- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`

## Stop
```bash
make down-offline
```
