# Настройки скрапера VesselFinder

## Описание

Файл содержит все настройки для работы скрапера судов с VesselFinder.

## Режимы работы

### MODE
Определяет режим работы скрапера:
- `"test"` - тестовый режим с ограничениями (по умолчанию)
- `"full"` - полноценный сбор данных

**Как изменить:** установите переменную окружения `SCRAPER_MODE` в docker-compose.yml

```yaml
vesselfinder_scraper:
  environment:
    SCRAPER_MODE: full  # или test
```

## Лимиты

- **MAX_VESSELS_TEST** - максимум судов в тестовом режиме (5)
- **MAX_VESSELS_FULL** - максимум судов в полном режиме (None = без ограничений)
- **MAX_PAGES** - максимум страниц для обработки (None = все)
- **MAX_RETRIES** - максимум попыток при ошибках (5)

## Задержки

- **REQUEST_DELAY_MIN/MAX** - задержка между запросами (3-8 сек)
- **RETRY_BASE_DELAY** - базовая задержка для экспоненциального роста при повторах (2)
- **DOM_STABILIZATION_MIN/MAX** - задержка для стабилизации DOM (0.8-1.6 сек)

## Timeouts

- **WAIT_TIMEOUT** - ожидание элементов страницы (12 сек)
- **PHOTO_DOWNLOAD_TIMEOUT** - загрузка фотографий (15 сек)

## Примеры использования

### Запуск в тестовом режиме (5 судов)
```bash
docker-compose up vesselfinder_scraper
```

### Запуск в полном режиме
Измените в docker-compose.yml:
```yaml
vesselfinder_scraper:
  environment:
    SCRAPER_MODE: full
```

### Изменение количества судов в тесте
Отредактируйте `config.py`:
```python
MAX_VESSELS_TEST = 10  # собрать 10 судов
```
