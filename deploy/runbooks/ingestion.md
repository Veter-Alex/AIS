# Ingestion Runbook

## Purpose
Run the ingestion node for continuous online data accumulation from maritime sources.

## Node role
- Ingestion node: collects and updates vessel data.

## Stack
- `db`
- `vessel_api`
- `marinetraffic_scraper`
- `myshiptracking_scraper`
- `maritime_database_scraper`

Compose profile: `deploy/compose/ingestion.yml`

## Start
```bash
make up-ingestion
```

## Verify
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/monitor/scrapers
curl http://localhost:8000/metrics
make logs-ingestion
```

## Stop
```bash
make down-ingestion
```
