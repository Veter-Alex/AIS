"""
Конфигурация скрапера VesselFinder.

Назначение:
- централизованно хранить лимиты, таймауты и задержки антиблокировочной стратегии;
- держать параметры Selenium и БД в одном месте;
- упростить переключение между test/full режимами.
"""

# Настройки скрапера VesselFinder

# Режим работы управляется переменной окружения SCRAPER_MODE ("test"/"full")

# Тип судов для фильтрации (None = все типы, 7 = Military)
VESSEL_TYPE = 7

# === Лимиты ===
# Максимальное количество судов для парсинга в тестовом режиме
MAX_VESSELS_TEST = 100

# Максимальное количество судов для парсинга в полном режиме (None = без ограничений)
MAX_VESSELS_FULL = None

# Максимальное количество страниц для обработки (None = все доступные)
MAX_PAGES = None

# Максимальное количество попыток при ошибках
MAX_RETRIES = 5

# === Задержки ===
# Задержка между запросами к страницам судов (секунды)
REQUEST_DELAY_MIN = 3
REQUEST_DELAY_MAX = 8

# Задержка между запросами к деталям отдельных судов (секунды)
DETAIL_DELAY_MIN = 2
DETAIL_DELAY_MAX = 4

# Задержка перед повторной попыткой после ошибки (базовое значение для экспоненциального роста)
RETRY_BASE_DELAY = 5

# Задержка для стабилизации DOM после загрузки (секунды)
DOM_STABILIZATION_MIN = 0.8
DOM_STABILIZATION_MAX = 1.6

# Дополнительная задержка каждые N страниц (эмуляция "отдыха")
BREAK_AFTER_PAGES = 30
BREAK_DURATION_MIN = 45
BREAK_DURATION_MAX = 90

# === Timeouts ===
# Таймаут ожидания элементов страницы (секунды)
WAIT_TIMEOUT = 12

# Таймаут загрузки фотографий (секунды)
PHOTO_DOWNLOAD_TIMEOUT = 15

# === User Agents ===
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# === Selenium настройки ===
CHROME_BINARY = "/usr/bin/chromium"
CHROMEDRIVER_BINARY = "/usr/bin/chromedriver"
WINDOW_SIZE = "1920,1080"

# === База данных ===
# Настройки подключения (переопределяются через ENV переменные)
DB_NAME = "vessels_db"
DB_USER = "user"
DB_PASSWORD = "password"
DB_HOST = "db"
DB_PORT = "5432"
