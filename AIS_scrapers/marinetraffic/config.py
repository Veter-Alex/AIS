"""
Конфигурация для скрапера MarineTraffic.

Описание:
- Настройки URL, пагинации, задержек и лимитов.
- User-Agent ротация для снижения риска блокировки.

Примечание по поддержке:
- файл используется как единая точка настройки поведения скрапера,
  поэтому изменения лимитов/таймаутов рекомендуется вносить именно здесь.
"""

# База URL для списка судов
BASE_URL = "https://www.marinetraffic.org/vessels"

# Параметры пагинации
VESSELS_PER_PAGE = 50  # По умолчанию 50 судов на странице
MAX_PAGES = None  # None = без ограничений

# Лимиты для режимов работы
MAX_VESSELS_TEST = 100  # Тестовый режим: 100 судов
MAX_VESSELS_FULL = None  # Полный режим: все суда (None = без ограничений)

# Задержки между запросами (секунды)
REQUEST_DELAY_MIN = 3.0
REQUEST_DELAY_MAX = 6.0

# Периодические перерывы
BREAK_AFTER_PAGES = 30  # Перерыв после каждых 30 страниц
BREAK_DURATION_MIN = 90  # Минимальная длительность перерыва (секунды)
BREAK_DURATION_MAX = 180  # Максимальная длительность перерыва (секунды)

# Повторные попытки при ошибках
MAX_RETRIES = 5
RETRY_DELAY_MIN = 5.0
RETRY_DELAY_MAX = 15.0

# User-Agent ротация
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Имя источника данных
DATA_SOURCE = "marinetraffic.org"
