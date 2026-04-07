# Синхронизация БД: PostgreSQL → SQLite

Скрипт для добавления недостающих записей из PostgreSQL в SQLite БД.

## Описание

Скрипт сравнивает данные в двух БД:
- **PostgreSQL** (`vessels_db`) — основная БД приложения
- **SQLite** (`ships_database.sqb`) — локальная резервная БД

Добавляет в SQLite только новые записи, которые есть в PostgreSQL, но отсутствуют в SQLite (по MMSI).

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Убедитесь, что PostgreSQL контейнер запущен:
```bash
docker compose up -d db
```

## Использование

### Сухой прогон (без изменений):
```bash
python sync_postgres_to_sqlite.py --dry-run
```

Покажет, сколько записей будет добавлено, без реальной вставки данных.

### Реальная синхронизация:
```bash
python sync_postgres_to_sqlite.py
```

Добавит все новые записи в SQLite.

## Параметры командной строки

```
--dry-run              Только показать, что будет сделано
--host HOST            Host PostgreSQL (по умолчанию: localhost)
--port PORT            Порт PostgreSQL (по умолчанию: 5432)
--db DATABASE          Имя БД (по умолчанию: vessels_db)
--user USER            Пользователь (по умолчанию: user)
--password PASSWORD    Пароль (по умолчанию: password)
```

### Пример с кастомным подключением:
```bash
python sync_postgres_to_sqlite.py --host 192.168.1.100 --port 5432 --password mypassword
```

## Маппинг полей

Данные маппируются следующим образом:

| PostgreSQL | SQLite | Примечание |
|---|---|---|
| mmsi | mmsi | Уникальный идентификатор |
| imo | imo | IMO номер |
| name | name | Имя судна |
| flag | country | Флаг/страна |
| detailed_type \| ship_type | type | Тип (приоритет на detailed_type) |
| call_sign | ship_class | Позывной |
| year_built | reserved_int | Год постройки |
| length, width, dwt, gt | reserved_text | Размеры (текстовое поле) |

## Логика

1. Подключается к обеим БД
2. Получает все MMSI из SQLite
3. Получает все судна из PostgreSQL
4. Фильтрует только новые (MMSI которых нет в SQLite)
5. Вставляет новые записи (или обновляет, если есть)
6. Коммитит изменения

## Примечания

- Скрипт использует `INSERT OR REPLACE`, поэтому при совпадении MMSI запись обновится
- Процесс может занять некоторое время при большом количестве записей (88k+ судов)
- Все ошибки логируются, но процесс продолжает работу
