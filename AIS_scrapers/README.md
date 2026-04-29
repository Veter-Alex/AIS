# AIS Scrapers

Набор скраперов для сбора данных о судах из нескольких источников:

- `marinetraffic`
- `maritime_database`
- `myshiptracking`
- `vesselfinder`

## Python окружение (.venv)

Для локального запуска используйте только изолированное окружение проекта.

Создание `.venv` (Python 3.11, как в CI и Docker):

```bash
py -3.11 -m venv .venv
```

Установка зависимостей всех скраперов + тестов:

```bash
.\.venv\Scripts\python.exe -m pip install -r AIS_scrapers/marinetraffic/requirements.txt -r AIS_scrapers/myshiptracking/requirements.txt -r AIS_scrapers/maritime_database/requirements.txt -r AIS_scrapers/vesselfinder/requirements.txt pytest
```

## Запуск тестов

Parser smoke/golden:

```bash
.\.venv\Scripts\python.exe -m pytest AIS_scrapers/tests/test_parser_smoke.py -q
```

## Локальный запуск скраперов

Примеры запуска через `.venv`:

```bash
set SCRAPER_MODE=test
.\.venv\Scripts\python.exe AIS_scrapers/marinetraffic/scraper.py
.\.venv\Scripts\python.exe AIS_scrapers/myshiptracking/scraper.py
.\.venv\Scripts\python.exe AIS_scrapers/maritime_database/scraper.py
.\.venv\Scripts\python.exe AIS_scrapers/vesselfinder/scraper.py
```

## Важные заметки

- Перед запуском убедитесь, что доступна PostgreSQL и применены миграции: из корня репозитория `alembic upgrade head` (те же правила, что для `vessel_api` в Docker).
- В скраперах включены preflight-проверки схемы (`vessels.mmsi UNIQUE`, `scraper_state(scraper_name, mode)`).
- Для production-проходов используйте Docker Compose и ENV-конфигурацию.

