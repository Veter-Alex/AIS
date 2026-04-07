# AIS Vessel Database

Проект для сбора, хранения, поиска и анализа данных о судах.

Система включает:
- PostgreSQL (с поддержкой pgvector);
- API по судам (vessel_api);
- AI Agent (RAG, retrieval, локальные LLM через Ollama);
- frontend на React + TypeScript;
- набор скраперов для разных источников.

## Актуальная структура

- ai_agent/ — AI-сервис (FastAPI, retrieval, RAG, управление LLM-моделями)
- vessel_api/ — основной API каталога судов
- vessel_frontend/ — веб-интерфейс (список, карточка, AI-страница)
- AIS_scrapers/ — скраперы:
	- marinetraffic/
	- maritime_database/
	- myshiptracking/
	- vesselfinder/
- sync_db_scripts/ — синхронизация PostgreSQL -> SQLite
- AIS_offline_package/ — offline-пакет развертывания
- data/ — локальные данные (PostgreSQL, изображения)

## Быстрый запуск

```bash
docker compose up -d
```

Сервисы по умолчанию:
- Frontend: http://localhost:3000
- Vessel API: http://localhost:8000
- AI Agent API: http://localhost:8100
- Ollama API: http://localhost:11434
- PostgreSQL: localhost:5432

Проверка здоровья AI Agent:

```bash
curl http://localhost:8100/health
```

## AI возможности

AI Agent поддерживает:
- retrieval режимы: hybrid, vector, lexical, exact;
- диагностику retrieval через /retrieve/diagnostics;
- RAG-ответы через /rag/answer;
- управление локальными моделями через:
	- /llm/models
	- /llm/pull-model
	- /llm/delete-model

Для видеокарт уровня 4 ГБ VRAM рекомендуется использовать компактные модели 3b в Q4.

## Локальная разработка frontend

```bash
cd vessel_frontend
npm install
npm run dev
```

## Полезные команды

Пересборка AI и frontend:

```bash
docker compose up -d --build ai_agent vessel_frontend
```

Просмотр логов AI:

```bash
docker compose logs -f ai_agent
```

## Миграция и offline

- Инструкции по миграции: README_MIGRATION.md
- Инструкции по БД: README_DB.txt
- Offline-развертывание: AIS_offline_package/DEPLOY_GUIDE.md

## Примечания по репозиторию

- Крупные локальные данные и служебные артефакты исключены через .gitignore.
- Для публикации в GitHub используется ветка main и удаленный origin.
