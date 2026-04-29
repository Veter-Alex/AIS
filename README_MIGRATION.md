# Миграция данных между online/offline узлами

## Основной workflow

Для переносов используйте контракт offline-пакета:

- спецификация: `deploy/runbooks/offline-package.md`
- экспорт: `deploy/offline/export_offline_bundle.sh`
- восстановление: `deploy/offline/restore_offline_bundle.sh`

Пример:

```bash
POSTGRES_USER=user POSTGRES_DB=vessels_db \
  deploy/offline/export_offline_bundle.sh v1

POSTGRES_USER=user POSTGRES_DB=vessels_db \
  deploy/offline/restore_offline_bundle.sh backups/offline_bundle_*.tar.gz
```

## Что переносится

- дамп данных PostgreSQL;
- метаданные пакета (`manifest.json`, версия контракта);
- дополнительные файлы из `extra/` (если включены в пакет).

## Базовый сценарий переноса

1. На исходном узле сформируйте пакет (`export_offline_bundle.sh`).
2. Передайте архив на целевой узел.
3. На целевом узле восстановите пакет (`restore_offline_bundle.sh`).
4. Проверьте доступность API и количество записей в БД.

Проверка:

```bash
docker compose -f deploy/compose/use-offline.yml exec db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM vessels;"
```

## Важные замечания

- Схема БД управляется Alembic; при запуске `vessel_api` применяется `alembic upgrade head`.
- Официальные профили запуска: `deploy/compose/ingestion.yml` и `deploy/compose/use-offline.yml`.
- Детали по миграциям схемы: `README_DB.txt`.
