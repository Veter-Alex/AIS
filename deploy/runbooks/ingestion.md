# Ingestion Mode Runbook

## Purpose
Continuous online data accumulation from maritime sources.

## Stack
- `db`
- `vessel_api`
- `marinetraffic_scraper`
- `myshiptracking_scraper`
- `maritime_database_scraper`

Compose file: `deploy/compose/ingestion.yml`

## Start
```bash
make up-ingestion
```

## Monitor
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
