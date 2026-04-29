PROJECT_ROOT := $(CURDIR)
INGESTION_COMPOSE := deploy/compose/ingestion.yml
OFFLINE_COMPOSE := deploy/compose/use-offline.yml

.PHONY: up-ingestion down-ingestion logs-ingestion up-offline down-offline logs-offline backup-db

up-ingestion:
	docker compose -f $(INGESTION_COMPOSE) up -d --build

down-ingestion:
	docker compose -f $(INGESTION_COMPOSE) down

logs-ingestion:
	docker compose -f $(INGESTION_COMPOSE) logs -f --tail=200

up-offline:
	docker compose -f $(OFFLINE_COMPOSE) up -d --build

down-offline:
	docker compose -f $(OFFLINE_COMPOSE) down

logs-offline:
	docker compose -f $(OFFLINE_COMPOSE) logs -f --tail=200

backup-db:
	@mkdir -p backups
	docker compose -f $(OFFLINE_COMPOSE) exec -T db pg_dump -U $$POSTGRES_USER $$POSTGRES_DB > backups/vessels_`date +%Y%m%d_%H%M%S`.sql
