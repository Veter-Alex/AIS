"""
Конфигурация скрапера Maritime Database.

Структура файла:
- лимиты и режимы работы;
- параметры пагинации и задержек;
- сетевые timeout/HTTP-настройки;
- параметры подключения к БД (с возможностью переопределения через ENV).
"""

# Настройки скрапера Maritime Database

# Режим работы управляется переменной окружения SCRAPER_MODE ("test"/"full")

# Тип судов для фильтрации (None = все типы)
VESSEL_TYPE = None

# === Лимиты ===
# Максимальное количество судов для парсинга в тестовом режиме
MAX_VESSELS_TEST = 100

# Максимальное количество судов для парсинга в полном режиме (None = без ограничений)
MAX_VESSELS_FULL = None

# Максимальное количество страниц для обработки (None = все доступные)
MAX_PAGES = None

# Максимальное количество попыток при ошибках
MAX_RETRIES = 5

# === Пагинация ===
# Количество судов на странице (по данным сайта)
VESSELS_PER_PAGE = 30

# Базовый URL
BASE_URL = "https://www.maritime-database.com/vessels"

# === Задержки ===
# Задержка между запросами к страницам (секунды)
REQUEST_DELAY_MIN = 3
REQUEST_DELAY_MAX = 7

# Задержка между запросами к деталям судна (секунды)
DETAIL_DELAY_MIN = 1
DETAIL_DELAY_MAX = 3

# Задержка перед повторной попыткой после ошибки (базовое значение для экспоненциального роста)
RETRY_BASE_DELAY = 5

# Дополнительная задержка каждые N страниц (эмуляция "отдыха")
BREAK_AFTER_PAGES = 50
BREAK_DURATION_MIN = 30
BREAK_DURATION_MAX = 60

# === Timeouts ===
# Таймаут HTTP запросов (секунды)
REQUEST_TIMEOUT = 30

# === HTTP настройки ===
# User Agents для ротации
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# === База данных ===
# Настройки подключения (переопределяются через ENV переменные)
DB_NAME = "vessels_db"
DB_USER = "user"
DB_PASSWORD = "password"
DB_HOST = "db"
DB_PORT = "5432"
