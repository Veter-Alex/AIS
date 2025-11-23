# Vessel Database - README

## Структура проекта

- `vessel_api/` - FastAPI backend
- `vessel_frontend/` - React + TypeScript frontend
- `vesselfinder_scraper/` - Selenium scraper для VesselFinder
- `data/` - данные (PostgreSQL, фото судов)

## Запуск

```bash
docker-compose up -d
```

Доступ:
- Frontend: http://localhost:3000
- API: http://localhost:8000
- PostgreSQL: localhost:5432

## Разработка frontend локально

Если нужно работать с фронтендом локально (вне Docker):

```bash
cd vessel_frontend
npm install
npm run dev
```

## Миграция данных

См. `README_MIGRATION.md` для инструкций по offline переносу системы.
