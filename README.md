# AIS Vessel Database

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-Enabled-2E8B57)](https://github.com/pgvector/pgvector)
[![Status](https://img.shields.io/badge/Status-Active%20Development-brightgreen)](#)

Проект для сбора, хранения, поиска и анализа данных о судах.

## О проекте

AIS - модульная платформа для сбора и обработки данных о судах, которая объединяет
ingestion из нескольких источников, хранение и API-доступ для морских задач.

Система включает:
- PostgreSQL (с поддержкой pgvector);
- API по судам (vessel_api);
- frontend на React + TypeScript;
- набор скраперов для разных источников.

## Актуальная структура

- vessel_api/ — основной API каталога судов
- vessel_frontend/ — веб-интерфейс (список и карточка судна)
- AIS_scrapers/ — скраперы:
	- marinetraffic/
	- maritime_database/
	- myshiptracking/
	- vesselfinder/
- data/ — локальные данные (PostgreSQL, изображения)

## Режимы запуска

Проект поддерживает два официальных режима:

1. **Ingestion mode (online):** `db + scrapers + vessel_api`  
   Для непрерывного накопления данных. Мониторинг через `/health`, `/ready`,
   `/monitor/scrapers`, `/metrics`.
2. **Use mode (offline/consumer):** `db + vessel_api + vessel_frontend`  
   Для просмотра, поиска, фильтрации, редактирования и ведения заметок.

Ключевые compose-профили:
- `deploy/compose/ingestion.yml`
- `deploy/compose/use-offline.yml`

## Быстрый запуск

```bash
docker compose up -d
```

Рекомендуемый запуск по профилям:

```bash
make up-ingestion
# или
make up-offline
```

## Развертывание на Raspberry Pi

Для долгого сбора данных (24/7) на Raspberry Pi используйте ingestion-профиль:

```bash
docker compose -f deploy/compose/ingestion.yml up -d --build
```

Он поднимает `db`, `vessel_api` и 3 скрапера в режиме `full`.
Подробная инструкция (`.env`, мониторинг, `systemd` автозапуск) в
**[DEPLOY_RPI.md](DEPLOY_RPI.md)**.

Сервисы по умолчанию:
- Frontend: http://localhost:3000
- Vessel API: http://localhost:8000
- PostgreSQL: localhost:5432

Проверка здоровья API:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

## Схема базы данных (Alembic)

Таблицы в `public` и схема `ai` описаны миграциями в каталоге **`alembic/`**. При **`docker compose up`** контейнер **`vessel_api`** перед запуском выполняет **`alembic upgrade head`**.

Локально (из корня репозитория), при уже запущенном PostgreSQL и переменных **`POSTGRES_*`** как в **`.env`**:

```bash
pip install -r vessel_api/requirements.txt
alembic upgrade head
```

Подробности по миграциям и проверке версии — в **[README_DB.txt](README_DB.txt)**.

## Заметки и синхронизация

API поддерживает заметки к карточке судна и синхронизацию между online/offline
узлами:
- `GET/POST /vessels/{imo}/notes`
- `PATCH/DELETE /notes/{note_uuid}`
- `POST /sync/notes/pull`
- `POST /sync/notes/push`

Runbook по синхронизации: **[deploy/runbooks/sync-notes.md](deploy/runbooks/sync-notes.md)**.

## Локальная разработка frontend

В репозитории зафиксирован **`package-lock.json`**. Как в CI — воспроизводимая установка:

```bash
cd vessel_frontend
npm ci
npm run dev
```

Если меняли **`package.json`**, обновите lock-файл: **`npm install`** и закоммитьте **`package-lock.json`**.

## Python окружение (.venv)

Для локальных Python-команд в проекте используйте изолированное окружение `.venv`
(Python 3.11 — как в Docker-образах и CI), а не глобальный интерпретатор.

Создание окружения (один раз):

```bash
py -3.11 -m venv .venv
```

Установка зависимостей скраперов и тестов:

```bash
.\.venv\Scripts\python.exe -m pip install -r AIS_scrapers/marinetraffic/requirements.txt -r AIS_scrapers/myshiptracking/requirements.txt -r AIS_scrapers/maritime_database/requirements.txt -r AIS_scrapers/vesselfinder/requirements.txt pytest
```

Запуск parser smoke/golden тестов:

```bash
.\.venv\Scripts\python.exe -m pytest AIS_scrapers/tests/test_parser_smoke.py -q
```

## Полезные команды

Пересборка frontend и API:

```bash
docker compose up -d --build vessel_frontend vessel_api
```

Профильные команды:

```bash
make up-ingestion
make logs-ingestion
make down-ingestion

make up-offline
make logs-offline
make down-offline
```

Просмотр логов API:

```bash
docker compose logs -f vessel_api
```

## Документация и runbooks

- Перенос данных между узлами: `README_MIGRATION.md`
- Работа с БД и Alembic: `README_DB.txt`
- Развертывание на Raspberry Pi: `DEPLOY_RPI.md`
- Runbook ingestion: `deploy/runbooks/ingestion.md`
- Runbook offline use: `deploy/runbooks/offline-use.md`
- Контракт offline package: `deploy/runbooks/offline-package.md`

## Примечания по репозиторию

- Крупные локальные данные и служебные артефакты исключены через .gitignore.
- Для публикации в GitHub используется ветка main и удаленный origin.
