"""
Конфигурация для скрапера MyShipTracking.

Описание:
- Настройки URL, пагинации, задержек и лимитов.
- User-Agent ротация для снижения риска блокировки.

Примечание по поддержке:
- при эксплуатации в Docker реальные параметры БД берутся из ENV,
  значения в этом файле выступают как локальные fallback'и.
"""

# База URL для списка судов
BASE_URL = "https://www.myshiptracking.com/vessels"

# Параметры пагинации
VESSELS_PER_PAGE = (
    50  # Используем pp=50 для 50 судов на странице (макс 10,000 за 200 страниц)
)
MAX_PAGES = None  # None = без ограничений

# Лимиты для режимов работы
MAX_VESSELS_TEST = 100  # Тестовый режим: 100 судов
MAX_VESSELS_FULL = None  # Полный режим: все суда (None = без ограничений)

# Задержки между запросами (секунды)
REQUEST_DELAY_MIN = 2.0
REQUEST_DELAY_MAX = 5.0

# Периодические перерывы
BREAK_AFTER_PAGES = 50  # Перерыв после каждых 50 страниц
BREAK_DURATION_MIN = 60  # Минимальная длительность перерыва (секунды)
BREAK_DURATION_MAX = 120  # Максимальная длительность перерыва (секунды)

# Повторные попытки при ошибках
MAX_RETRIES = 5
RETRY_BASE_DELAY = 5  # Базовая задержка для экспоненциального бэкоффа (секунды)

# Таймаут запросов
REQUEST_TIMEOUT = 30

# User-Agent ротация
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

# Настройки базы данных (будут переопределены через ENV в Docker)
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "ais_db"
DB_USER = "ais_user"
DB_PASSWORD = "ais_password"
