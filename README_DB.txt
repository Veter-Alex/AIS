# Работа с PostgreSQL и схемой (Alembic)

Схема БД поддерживается миграциями Alembic из каталога `alembic/`.
При запуске `vessel_api` автоматически выполняется `alembic upgrade head`.

## Compose-профили

- ingestion: `deploy/compose/ingestion.yml`
- offline-use: `deploy/compose/use-offline.yml`

## Стандартный сценарий (рекомендуется)

Запустите нужный профиль через `make` или `docker compose` — отдельный ручной прогон SQL не требуется.

## Локальный прогон миграций (хост)

Из корня репозитория:

```bash
pip install -r vessel_api/requirements.txt
alembic upgrade head
```

Перед запуском задайте `POSTGRES_*` переменные (аналогично `.env`), например:

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=vessels_db
POSTGRES_USER=user
POSTGRES_PASSWORD=password
```

## Полезные проверки

Повторно применить миграции в запущенном API-контейнере:

```bash
docker compose -f deploy/compose/use-offline.yml exec vessel_api alembic upgrade head
```

Проверить текущую версию миграций:

```bash
docker compose -f deploy/compose/use-offline.yml exec db psql -U user -d vessels_db -c "SELECT * FROM alembic_version;"
```

## Справка по старой инициализации

Историческая SQL-версия хранится в `docs/legacy/init.sql` и не участвует в текущем процессе развертывания.
