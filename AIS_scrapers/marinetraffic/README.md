# MarineTraffic Scraper

Скрапер для сбора данных о судах с сайта [marinetraffic.org](https://www.marinetraffic.org/vessels).

## Описание

MarineTraffic - один из крупнейших источников данных о судах в мире, содержащий более **250,000 судов**. Скрапер собирает:

- **Базовые данные**: название, MMSI, IMO, флаг, тип судна
- **Технические характеристики**: длина, ширина, GT, DWT, год постройки
- **Фотографии**: скачиваются и сжимаются до 320x240 с качеством 65%

## Приоритет источника

**Приоритет: 1** (самый высокий) - данные из MarineTraffic имеют наивысший приоритет при сохранении в БД.

## Структура

```
marinetraffic/
├── scraper.py          # Основной скрипт скрапера
├── config.py           # Конфигурация (URL, задержки, лимиты)
├── requirements.txt    # Python зависимости
├── Dockerfile          # Docker образ
└── README.md           # Эта документация
```

## Особенности

### Пагинация
- URL формат: `https://www.marinetraffic.org/vessels?page=N&status=Any%20Service%20Status`
- Страница 1: `?page=1&status=Any%20Service%20Status`
- Страница 2: `?page=2&status=Any%20Service%20Status`
- И так далее...

### Парсинг
1. **Страница списка**: извлекает название, флаг, тип, ссылку на детальную страницу
2. **Детальная страница**: извлекает MMSI, IMO, технические характеристики, фото

### Задержки и лимиты
- Задержка между страницами: **3-6 секунд**
- Задержка между детальными страницами: **1-3 секунды**
- Перерыв каждые **30 страниц**: 90-180 секунд
- Повторные попытки: **5 попыток** с задержкой 5-15 секунд

### 404 обработка
- Останавливается после **10 последовательных 404 ошибок**
- Предполагает окончание доступных данных

### Многопоточность
- Используется **4 потока** для параллельной обработки судов на одной странице
- Ускоряет сбор данных в ~4 раза

## Запуск

### Через Docker Compose (рекомендуется)

```bash
# Запустить все сервисы (БД + скраперы + API + фронтенд)
docker compose up -d

# Смотреть логи скрапера
docker compose logs -f marinetraffic_scraper

# Перезапустить скрапер
docker compose restart marinetraffic_scraper

# Остановить скрапер
docker compose stop marinetraffic_scraper
```

### Режимы работы

Задаётся через переменную окружения `SCRAPER_MODE`:

- `test` - собрать первые 100 судов (для тестирования)
- `full` - собрать все доступные суда (по умолчанию)

Изменить в `docker-compose.yml`:
```yaml
environment:
  SCRAPER_MODE: "test"  # или "full"
```

## Прогресс

Скрапер сохраняет своё состояние в таблице `scraper_state`:
- Последняя обработанная страница
- Количество обработанных судов
- Режим работы (test/full)

При перезапуске продолжает с последней страницы.

### Проверить состояние

```bash
# Подключиться к БД
docker compose exec db psql -U user -d vessels_db

# Проверить состояние
SELECT * FROM scraper_state WHERE scraper_name = 'marinetraffic.org';

# Сбросить состояние (начать с начала)
DELETE FROM scraper_state WHERE scraper_name = 'marinetraffic.org' AND mode = 'full';
```

## Конфигурация

Настройки в `config.py`:

```python
BASE_URL = "https://www.marinetraffic.org/vessels"
VESSELS_PER_PAGE = 50
REQUEST_DELAY_MIN = 3.0
REQUEST_DELAY_MAX = 6.0
BREAK_AFTER_PAGES = 30
BREAK_DURATION_MIN = 90
BREAK_DURATION_MAX = 180
MAX_RETRIES = 5
```

## База данных

### Приоритет источников

MarineTraffic имеет **приоритет 1** (самый высокий):

```sql
SELECT source_name, source_priority, description 
FROM data_sources 
ORDER BY source_priority;
```

Результат:
```
marinetraffic.org       | 1 | Основной источник - самая полная база данных судов
maritime-database.com   | 2 | Общая база данных судов
vesselfinder.com        | 3 | Наиболее детальные данные
myshiptracking.com      | 4 | Дополнительные данные
```

### UPSERT логика

При конфликте MMSI:
- Данные **обновляются**, если источник имеет **более высокий приоритет**
- Пустые поля **заполняются** новыми данными (не затирают существующие)
- IMO, год постройки, размеры - **дополняют** (COALESCE)

## Статистика

Проверить количество судов из MarineTraffic:

```sql
SELECT data_source, COUNT(*) 
FROM vessels 
GROUP BY data_source 
ORDER BY COUNT(*) DESC;
```

## Примеры URL

- Список судов (страница 1): https://www.marinetraffic.org/vessels?page=1&status=Any%20Service%20Status
- Список судов (страница 2): https://www.marinetraffic.org/vessels?page=2&status=Any%20Service%20Status
- Детальная страница судна: https://www.marinetraffic.org/ship-owner-manager-ism-data/MSC-MARIELLA/9934747/636022920

## Troubleshooting

### Ошибка "No vessels found on page"
- Возможно изменилась структура HTML
- Проверить URL вручную в браузере
- Обновить парсинг логику в `parse_vessel_list_page()`

### Ошибка "Failed to fetch page"
- Проверить доступность сайта
- Увеличить задержки между запросами
- Проверить User-Agent (возможна блокировка)

### Слишком медленно
- Увеличить `max_workers` в ThreadPoolExecutor (текущее: 4)
- Уменьшить задержки (осторожно, может привести к блокировке)

### Блокировка IP
- Увеличить задержки между запросами
- Увеличить длительность перерывов
- Использовать прокси (требуется модификация кода)

## License

MIT
