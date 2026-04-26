# Работа с PostgreSQL и схемой (Alembic)

# Схема БД (таблицы public.* и ai.*) задаётся миграциями Alembic в каталоге alembic/.
# Файл init.sql в корне репозитория устарел и не монтируется в docker-compose;
# он оставлен только для справки и ручных сценариев.

# --- Docker Compose (рекомендуется)
# При старте контейнера vessel_api выполняется: alembic upgrade head, затем uvicorn.
# Отдельно накатывать SQL обычно не нужно.

# --- Локально (хост), из корня репозитория
# Установить зависимости миграций (те же, что у vessel_api):
#   pip install -r vessel_api/requirements.txt
# Переменные окружения как в .env, но для локального Postgres:
#   POSTGRES_HOST=localhost
#   POSTGRES_PORT=5432
#   POSTGRES_DB=vessels_db
#   POSTGRES_USER=user
#   POSTGRES_PASSWORD=password
# Применить миграции:
#   alembic upgrade head

# --- Вручную из уже запущенного контейнера API (если нужен повторный прогон)
# docker compose exec vessel_api alembic upgrade head

# --- Проверка версии миграций в БД
# docker compose exec db psql -U user -d vessels_db -c "SELECT * FROM alembic_version;"

# Старый способ через init.sql в entrypoint Postgres больше не используется:
#   ~~docker exec -i <container_id> psql ... < init.sql~~
#   ~~volume: ./init.sql:/docker-entrypoint-initdb.d/init.sql~~
