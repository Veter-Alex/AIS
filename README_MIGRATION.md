# Миграция данных на другой компьютер (offline)

## Текущая структура

Все данные хранятся на хосте в папке `data/`:

```
E:\Programming\Projects\Python\AIS\
├── data/
│   ├── postgres/          # База данных PostgreSQL (том Docker)
│   └── vessel_images/     # Фотографии судов
├── docker-compose.yml
├── alembic/                 # Миграции схемы БД (применяются при старте vessel_api)
├── alembic.ini
├── init.sql                 # Справочно; схема из docker-compose задаётся через Alembic
├── ais_shared/            # Общий код API (пул БД, логи)
├── vessel_api/
├── ai_agent/
└── AIS_scrapers/
```

Схема (`vessels`, `source_priority`, `scraper_state`, `ai.*`) накатывается командой **`alembic upgrade head`** (автоматически в контейнере `vessel_api` при `docker compose up`). При переносе каталога `data/postgres/` на новую машину **миграции уже «внутри» данных**; на чистой БД перед первым запуском API нужно один раз выполнить миграции (см. `README_DB.txt`).

## Подготовка к переносу (на машине с интернетом)

### 1. Остановить контейнеры
```powershell
docker compose down
```

### 2. Архивировать данные
```powershell
# Архивировать базу данных и изображения
Compress-Archive -Path data -DestinationPath ais_data_backup.zip

# Опционально: весь проект целиком
Compress-Archive -Path . -DestinationPath ais_full_backup.zip -Exclude data,__pycache__,.git
```

### 3. Сохранить Docker образы (если на целевой машине нет интернета)
```powershell
# Создать папку для образов
New-Item -ItemType Directory -Force -Path docker_images

# Сохранить образы (имена тегов подставьте из docker images)
docker save pgvector/pgvector:pg15 -o docker_images/pgvector_pg15.tar
docker save ais-vessel_api:latest -o docker_images/vessel_api.tar
docker save ais-ai_agent:latest -o docker_images/ai_agent.tar

# Архивировать образы
Compress-Archive -Path docker_images -DestinationPath docker_images.zip
```

## Перенос на другой компьютер (offline)

### 1. Скопировать файлы
Перенести на целевую машину:
- `ais_data_backup.zip` (данные)
- `ais_full_backup.zip` (код проекта, если нужен)
- `docker_images.zip` (Docker образы)

### 2. Распаковать на новой машине
```powershell
# Распаковать проект
Expand-Archive -Path ais_full_backup.zip -DestinationPath C:\AIS

# Перейти в папку проекта
cd C:\AIS

# Распаковать данные
Expand-Archive -Path ais_data_backup.zip -DestinationPath .

# Распаковать образы
Expand-Archive -Path docker_images.zip -DestinationPath .
```

### 3. Загрузить Docker образы
```powershell
docker load -i docker_images/pgvector_pg15.tar
docker load -i docker_images/vessel_api.tar
docker load -i docker_images/ai_agent.tar
```

### 4. Запустить контейнеры
```powershell
docker compose up -d
```

### 5. Проверить работу
```powershell
# Проверить количество записей
docker compose exec db psql -U user -d vessels_db -c "SELECT COUNT(*) FROM vessels;"

# Проверить примеры записей
docker compose exec db psql -U user -d vessels_db -c "SELECT name, imo, length, width FROM vessels LIMIT 3;"

# Проверить изображения
Get-ChildItem data/vessel_images
```

## Работа с БД на новой машине

### Подключение к БД
```powershell
# Через psql в контейнере
docker compose exec db psql -U user -d vessels_db

# Через pgAdmin или другие GUI инструменты:
# Host: localhost
# Port: 5432
# Database: vessels_db
# User: user
# Password: password
```

### Экспорт данных в SQL
```powershell
# Экспорт всей БД
docker compose exec db pg_dump -U user vessels_db > vessels_backup.sql

# Экспорт только структуры
docker compose exec db pg_dump -U user --schema-only vessels_db > vessels_schema.sql

# Экспорт только данных
docker compose exec db pg_dump -U user --data-only vessels_db > vessels_data.sql
```

### Экспорт данных в CSV
```powershell
# Через docker compose exec
docker compose exec db psql -U user -d vessels_db -c "\COPY vessels TO '/tmp/vessels.csv' WITH CSV HEADER"
docker cp ais-db-1:/tmp/vessels.csv ./vessels_export.csv

# Или напрямую из psql:
docker compose exec db psql -U user -d vessels_db
\COPY vessels TO '/tmp/vessels.csv' WITH CSV HEADER
```

## Резервное копирование

### Автоматическое резервное копирование БД (PowerShell)
```powershell
# Создать скрипт backup.ps1
$date = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupFile = "backups/vessels_$date.sql"
New-Item -ItemType Directory -Force -Path backups
docker compose exec -T db pg_dump -U user vessels_db > $backupFile
Write-Host "Backup created: $backupFile"

# Запланировать через Task Scheduler для регулярного выполнения
```

### Ручное копирование папки data/
```powershell
# Простейший способ - копирование папки целиком (контейнеры должны быть остановлены)
docker compose down
Copy-Item -Path data -Destination "D:\Backups\AIS_$(Get-Date -Format 'yyyy-MM-dd')" -Recurse
docker compose up -d
```

## Размер данных

Текущий размер:
- БД PostgreSQL: ~50-100 MB (зависит от количества записей)
- Изображения: ~1-5 MB на судно
- Для 1000 судов: ~1-5 GB данных

## Примечания

1. **Права доступа (Linux)**: На Linux может потребоваться:
   ```bash
   sudo chown -R 999:999 data/postgres
   ```

2. **Производительность**: Bind mounts на Windows/Mac медленнее именованных volumes, но для данного объёма данных разница незаметна.

3. **Портативность**: Пути в `docker-compose.yml` относительные (`./data/...`), поэтому проект можно разместить в любой папке.

4. **Безопасность**: Для production измените пароли в `docker-compose.yml` и используйте `.env` файл.

5. **API доступ к изображениям**: API имеет read-only доступ к папке с изображениями через volume mount.
