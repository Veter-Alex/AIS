"""
Скрапер MyShipTracking.

Описание:
- Загружает списки судов со страниц пагинации.
- Извлекает базовые поля: имя, MMSI, тип, флаг, текущую позицию, скорость, пункт назначения.
- Сохраняет в базу данных с "умным" upsert (не затирает данные из других источников).
- Реализованы задержки, повторные попытки и многопоточность для оптимизации.

Стиль:
- Докстринги и комментарии на русском языке в соответствии с PEP8.
"""

import io
import logging
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import config
import psycopg2
import requests
from bs4 import BeautifulSoup
from common.http import fetch_page_with_retry
from common.logging_utils import log_event
from common.metrics import RuntimeMetrics
from common.normalize import parse_int
from common.schema import validate_scraper_schema
from common.upsert import source_priority_sql
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Глобальная сессия для переиспользования соединений
session = requests.Session()
PLACEHOLDER_VALUES = {"", "-", "n/a", "na", "none", "unknown", "not available"}


def normalize_mmsi(raw):
    """Привести MMSI к виду ровно 9 цифр."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return digits if len(digits) == 9 else None


def normalize_vessel_name(raw):
    """Очистить имя судна от служебных хвостов IMO/MMSI."""
    if raw is None:
        return None
    name = str(raw).strip()
    if not name:
        return None
    name = re.sub(r"(?:IMO|MMSI)\s*:?\s*\d+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" -,:;/")
    return name or None


def normalize_label_text(raw):
    """Нормализовать текстовые поля и убрать placeholder значения."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    if text.lower() in PLACEHOLDER_VALUES:
        return None
    text = re.sub(r"(?:IMO|MMSI)\s*:?\s*\d+", "", text, flags=re.IGNORECASE)
    text = text.strip(" -,:;/")
    if text.lower() in PLACEHOLDER_VALUES:
        return None
    return text or None


def sanitize_numeric(value, *, min_value=None, max_value=None):
    if value is None:
        return None
    ivalue = parse_int(value)
    if ivalue is None:
        return None
    if min_value is not None and ivalue < min_value:
        return None
    if max_value is not None and ivalue > max_value:
        return None
    return ivalue


def choose_worker_count(last_page_error_ratio: float, recent_retry_count: int) -> int:
    if last_page_error_ratio > 0.65 or recent_retry_count >= 20:
        return 2
    if last_page_error_ratio > 0.4 or recent_retry_count >= 12:
        return 3
    if last_page_error_ratio < 0.15 and recent_retry_count <= 3:
        return 6
    if last_page_error_ratio < 0.25 and recent_retry_count <= 6:
        return 5
    return 4


def validate_vessel_payload(vessel_data, metrics):
    vessel_data["name"] = normalize_vessel_name(vessel_data.get("name"))
    vessel_data["flag"] = normalize_label_text(vessel_data.get("flag"))
    vessel_data["general_type"] = normalize_label_text(vessel_data.get("general_type"))
    vessel_data["detailed_type"] = normalize_label_text(vessel_data.get("detailed_type"))
    vessel_data["mmsi"] = normalize_mmsi(vessel_data.get("mmsi"))

    if not vessel_data.get("name"):
        metrics.empty_name += 1
        return False
    if not vessel_data.get("mmsi"):
        metrics.invalid_mmsi += 1
        return False

    vessel_data["year_built"] = sanitize_numeric(
        vessel_data.get("year_built"), min_value=1800, max_value=datetime.now().year + 1
    )
    vessel_data["length"] = sanitize_numeric(vessel_data.get("length"), min_value=10, max_value=500)
    vessel_data["width"] = sanitize_numeric(vessel_data.get("width"), min_value=2, max_value=90)
    vessel_data["gt"] = sanitize_numeric(vessel_data.get("gt"), min_value=50, max_value=600000)
    vessel_data["dwt"] = sanitize_numeric(vessel_data.get("dwt"), min_value=100, max_value=700000)
    return True


def download_image(photo_url, vessel_key):
    """Скачать изображение судна, сжать и сохранить.

    Параметры:
    - photo_url: URL изображения.
    - vessel_key: ключ для имени файла (обычно MMSI).

    Возвращает:
    - Путь к сохранённому файлу или None в случае ошибки.
    """
    if not photo_url or not vessel_key:
        return None

    image_dir = os.getenv("IMAGE_DIR", "/app/images")
    os.makedirs(image_dir, exist_ok=True)

    file_name = f"{vessel_key}.jpg"  # Все фото сохраняем как JPEG для сжатия
    dest = os.path.join(image_dir, file_name)

    try:
        headers = {"User-Agent": random.choice(config.USER_AGENTS)}
        r = session.get(photo_url, headers=headers, timeout=config.REQUEST_TIMEOUT)
        if r.status_code == 200:
            # Открыть изображение в памяти
            img = Image.open(io.BytesIO(r.content))

            # Конвертировать в RGB (для JPEG)
            if img.mode in ("RGBA", "LA", "P"):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = rgb_img

            # Сжать размер (макс 320x240)
            img.thumbnail((320, 240), Image.Resampling.LANCZOS)

            # Сохранить с качеством 65% (экономия ~70% размера)
            img.save(dest, "JPEG", quality=65, optimize=True)
            logging.info(f"Photo saved: {dest}")
            return dest
        else:
            logging.warning(
                f"Photo not downloaded, status={r.status_code} for {photo_url}"
            )
            return None
    except Exception as e:
        logging.warning(f"Error downloading/compressing photo: {e}")
        return None


def get_db_conn():
    """Создать подключение к базе данных PostgreSQL.

    Источник настроек: ENV переменные или `config.py`.
    Пользователь должен закрывать соединение после использования.
    """
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", config.DB_NAME),
        user=os.getenv("POSTGRES_USER", config.DB_USER),
        password=os.getenv("POSTGRES_PASSWORD", config.DB_PASSWORD),
        host=os.getenv("POSTGRES_HOST", config.DB_HOST),
        port=os.getenv("POSTGRES_PORT", config.DB_PORT),
    )


def get_scraper_state(mode):
    """Загрузить состояние скрапера для указанного режима.

    Параметры:
    - mode: строка режима (например, "test" или "full").

    Возвращает:
    - Кортеж `(last_page, vessels_count)`.
    Если записи нет — `(1, 0)`.
    """
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT last_page, vessels_count FROM scraper_state WHERE scraper_name = %s AND mode = %s",
            ("myshiptracking", mode),
        )
        result = cur.fetchone()
        if result:
            last_page, vessels_count = result
            logging.info(
                f"Loaded state for mode '{mode}': page {last_page}, vessels {vessels_count}"
            )
            return last_page, vessels_count
        logging.info(f"No state found for mode '{mode}', starting from beginning")
        return 1, 0
    finally:
        cur.close()
        conn.close()


def save_scraper_state(mode, last_page, vessels_count):
    """Сохранить состояние скрапера.

    Параметры:
    - mode: режим работы.
    - last_page: последняя обработанная страница.
    - vessels_count: общее число обработанных судов.
    """
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO scraper_state (scraper_name, mode, last_page, vessels_count, last_run_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (scraper_name, mode) DO UPDATE SET
                last_page = EXCLUDED.last_page,
                vessels_count = EXCLUDED.vessels_count,
                last_run_at = EXCLUDED.last_run_at
            """,
            ("myshiptracking", mode, last_page, vessels_count),
        )
        conn.commit()
        logging.info(
            f"State saved: mode '{mode}', page {last_page}, vessels {vessels_count}"
        )
    finally:
        cur.close()
        conn.close()


def save_vessel(vessel):
    """Сохранить или обновить судно в базе данных.

    Реализует "умный" upsert:
    - Поля обновляются по принципу COALESCE (не затираем существующие
        значимыми None).
    - Предпочтение источнику `vesselfinder.com`, если он уже указан
        в существующей записи.

    Параметры:
    - vessel: словарь с полями судна.

    Возвращает:
    - True при успешной записи, False при ошибке.
    """
    if not vessel.get("mmsi"):
        logging.warning(f"Skipping vessel without MMSI: {vessel.get('name')}")
        return False

    conn = get_db_conn()
    cur = conn.cursor()
    incoming_prio = source_priority_sql("EXCLUDED.info_source")
    existing_prio = source_priority_sql("vessels.info_source")
    try:
        cur.execute(
            f"""
            INSERT INTO vessels (
                name, imo, mmsi, call_sign, general_type, detailed_type, flag, 
                year_built, length, width, dwt, gt, home_port, photo_url, photo_path,
                description, info_source, updated_at, vessel_key
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s
            )
            ON CONFLICT (mmsi) DO UPDATE SET
                name=COALESCE(EXCLUDED.name, vessels.name),
                imo=COALESCE(EXCLUDED.imo, vessels.imo),
                call_sign=COALESCE(EXCLUDED.call_sign, vessels.call_sign),
                general_type=COALESCE(EXCLUDED.general_type, vessels.general_type),
                detailed_type=COALESCE(EXCLUDED.detailed_type, vessels.detailed_type),
                flag=COALESCE(EXCLUDED.flag, vessels.flag),
                year_built=COALESCE(EXCLUDED.year_built, vessels.year_built),
                length=COALESCE(EXCLUDED.length, vessels.length),
                width=COALESCE(EXCLUDED.width, vessels.width),
                dwt=COALESCE(EXCLUDED.dwt, vessels.dwt),
                gt=COALESCE(EXCLUDED.gt, vessels.gt),
                home_port=COALESCE(EXCLUDED.home_port, vessels.home_port),
                photo_url=COALESCE(EXCLUDED.photo_url, vessels.photo_url),
                photo_path=COALESCE(EXCLUDED.photo_path, vessels.photo_path),
                description=COALESCE(EXCLUDED.description, vessels.description),
                info_source=CASE 
                    WHEN {existing_prio} <= {incoming_prio} THEN vessels.info_source
                    ELSE EXCLUDED.info_source
                END,
                updated_at=NOW(),
                vessel_key=COALESCE(EXCLUDED.vessel_key, vessels.vessel_key)
            """,
            (
                vessel.get("name"),
                vessel.get("imo"),
                vessel.get("mmsi"),
                vessel.get("call_sign"),
                vessel.get("general_type"),
                vessel.get("detailed_type"),
                vessel.get("flag"),
                vessel.get("year_built"),
                vessel.get("length"),
                vessel.get("width"),
                vessel.get("dwt"),
                vessel.get("gt"),
                vessel.get("home_port"),
                vessel.get("photo_url"),
                vessel.get("photo_path"),
                vessel.get("description"),
                "myshiptracking.com",
                vessel.get("vessel_key"),
            ),
        )
        conn.commit()
        logging.info(f"Saved vessel: {vessel.get('name')} (MMSI: {vessel.get('mmsi')})")
        return True
    except Exception as e:
        logging.error(f"Error saving vessel {vessel.get('name')}: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def fetch_page(url, metrics=None):
    """Загрузить страницу по URL с логикой повторных попыток.

    Использует общий `requests.Session` для переиспользования соединений.

    Параметры:
    - url: адрес страницы.
    - retries: текущий номер попытки (для рекурсивного экспоненциального бэкоффа).

    Возвращает:
    - Текст HTML или None при неудаче после `config.MAX_RETRIES`.
    - Специальное значение "404_NOT_FOUND" при ошибке 404 (для пропуска страницы).
    """
    def _on_retry(_url, _attempt, _max_attempts, _kind):
        if metrics is not None:
            metrics.retry_count += 1

    page = fetch_page_with_retry(
        session=session,
        url=url,
        user_agents=config.USER_AGENTS,
        timeout=config.REQUEST_TIMEOUT,
        max_retries=config.MAX_RETRIES,
        retry_base_delay=config.RETRY_BASE_DELAY,
        return_404_marker=True,
        on_retry=_on_retry,
    )
    if page is None and metrics is not None:
        metrics.http_failures += 1
    return page


def parse_vessel_list_page(html):
    """Распарсить страницу списка судов и вернуть данные.

    Параметры:
    - html: HTML страницы каталога.

    Возвращает список словарей с полями:
    - name, mmsi, general_type, flag, vessel_url.

    Примечание:
    - строки без пары `name + mmsi` отбрасываются как неполные.
    """
    soup = BeautifulSoup(html, "html.parser")
    vessels = []

    # Найти все строки таблицы с судами
    # MyShipTracking использует таблицу с классом или id, попробуем универсальный подход
    rows = soup.find_all("tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # Извлечь данные из ячеек таблицы
        # Структура: Flag+Name | MMSI | Type | Location | Speed | Destination | Time
        name_cell = cells[0]
        mmsi_cell = cells[1] if len(cells) > 1 else None
        type_cell = cells[2] if len(cells) > 2 else None

        # Извлечь имя судна и URL страницы деталей (может быть в ссылке)
        vessel_name = None
        vessel_url = None
        if name_cell:
            link = name_cell.find("a")
            if link:
                vessel_name = normalize_vessel_name(link.text.strip())
                href = link.get("href")
                if href:
                    # Собрать полный URL
                    if href.startswith("http"):
                        vessel_url = href
                    else:
                        vessel_url = "https://www.myshiptracking.com" + href
            else:
                vessel_name = normalize_vessel_name(name_cell.get_text(strip=True))

        # Извлечь MMSI
        vessel_mmsi = normalize_mmsi(mmsi_cell.get_text(strip=True) if mmsi_cell else None)

        # Извлечь тип судна
        vessel_type = normalize_label_text(type_cell.get_text(strip=True) if type_cell else None)

        # Извлечь флаг из img или title атрибута в первой ячейке
        vessel_flag = None
        if name_cell:
            flag_img = name_cell.find("img", {"title": True})
            if flag_img:
                vessel_flag = normalize_label_text(flag_img.get("title", "").strip())

        # Пропустить строки без имени или MMSI
        if not vessel_name or not vessel_mmsi:
            continue

        vessels.append(
            {
                "name": vessel_name,
                "mmsi": vessel_mmsi,
                "general_type": vessel_type,
                "flag": vessel_flag,
                "url": vessel_url,
                "vessel_key": vessel_mmsi,
            }
        )

    return vessels


def parse_vessel_detail_page(html, vessel_data):
    """Распарсить страницу деталей судна и дополнить данные.

    Параметры:
    - html: HTML страницы деталей.
    - vessel_data: словарь данных из списка (будет дополнен/уточнён).

    Возвращает:
    - Обновлённый словарь `vessel_data`.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    def extract_field(pattern, group=1):
        """Извлечь значение поля по регулярному выражению.

        Параметры:
        - pattern: паттерн регулярного выражения.
        - group: номер группы для возврата.
        """
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return m.group(group).strip() if m else None

    # Извлечь IMO (формат: IMO | 9263693)
    imo = extract_field(r"IMO\s*\|\s*(\d{7})")
    if not imo:
        imo = extract_field(r"IMO[:\s]+(\d{7})")
    if imo:
        vessel_data["imo"] = imo

    # Извлечь MMSI (формат: MMSI | 477642800)
    mmsi = extract_field(r"MMSI\s*\|\s*(\d{9})")
    if not mmsi:
        mmsi = extract_field(r"MMSI[:\s]+(\d{9})")
    if mmsi and not vessel_data.get("mmsi"):
        vessel_data["mmsi"] = mmsi

    # Извлечь Call Sign (формат: Call Sign | VRTV6)
    call_sign = extract_field(r"Call\s*Sign\s*\|\s*([A-Z0-9]+)")
    if not call_sign:
        call_sign = extract_field(r"Call\s*Sign[:\s]+([A-Z0-9]+)")
    if call_sign:
        vessel_data["call_sign"] = call_sign

    # Извлечь год постройки (формат: Build | 2003 ( 22 years old ))
    year_built = extract_field(r"Build\s*\|\s*(\d{4})")
    if not year_built:
        year_built = extract_field(r"(?:Year\s*Built|Build)[:\s]+(\d{4})")
    if year_built:
        vessel_data["year_built"] = sanitize_numeric(
            year_built, min_value=1800, max_value=datetime.now().year + 1
        )

    # Извлечь размеры (формат: Size | 183 x 32 m)
    size_match = re.search(r"Size\s*\|\s*(\d+)\s*x\s*(\d+)", text, re.IGNORECASE)
    if size_match:
        vessel_data["length"] = sanitize_numeric(size_match.group(1), min_value=10, max_value=500)
        vessel_data["width"] = sanitize_numeric(size_match.group(2), min_value=2, max_value=90)

    # Извлечь DWT (формат: DWT | 46,219 Tons)
    dwt = extract_field(r"DWT\s*\|\s*([\d,]+)")
    if dwt:
        vessel_data["dwt"] = sanitize_numeric(dwt, min_value=100, max_value=700000)

    # Извлечь GT (формат: GT | 30,024 Tons)
    gt = extract_field(r"GT\s*\|\s*([\d,]+)")
    if gt:
        vessel_data["gt"] = sanitize_numeric(gt, min_value=50, max_value=600000)

    # Извлечь тип из подзаголовка (например "Oil/Chemical Tanker")
    detailed_type = None
    h2_tags = soup.find_all("h2")
    for h2 in h2_tags:
        h2_text = h2.get_text(strip=True)
        # Пропустить заголовки навигации
        if (
            h2_text
            and len(h2_text) > 3
            and h2_text not in ["Info", "Weather", "Events"]
        ):
            detailed_type = normalize_label_text(h2_text)
            break
    if detailed_type and not vessel_data.get("detailed_type"):
        vessel_data["detailed_type"] = detailed_type

    # Попытаться найти фото судна на странице деталей
    # MyShipTracking хранит фото на photos.myshiptracking.com
    photo_found = False

    img_tags = soup.find_all("img")
    for img in img_tags:
        src = img.get("src", "")
        # Искать фото на photos.myshiptracking.com
        if "photos.myshiptracking.com" in src and "/vessel/" in src:
            if src.startswith("http"):
                photo_url = src
            else:
                photo_url = (
                    "https:" + src
                    if src.startswith("//")
                    else "https://www.myshiptracking.com" + src
                )

            # Попробовать скачать фото
            vessel_key = vessel_data.get("imo") or vessel_data.get("mmsi")
            if vessel_key:
                photo_path = download_image(photo_url, vessel_key)
                if photo_path:
                    vessel_data["photo_url"] = photo_url
                    vessel_data["photo_path"] = photo_path
                    photo_found = True
                    logging.info(
                        f"Found and downloaded photo for {vessel_data.get('name')}"
                    )
                    break

    if not photo_found:
        logging.debug(
            f"No photo found for vessel {vessel_data.get('name')} (MMSI: {vessel_data.get('mmsi')})"
        )

    return vessel_data


def process_vessel(vessel_data, metrics, detail_cache, cache_lock):
    """Обработать одно судно: загрузить детали (если есть URL), распарсить и сохранить.

    Включает небольшую случайную задержку для рассинхронизации потоков.

    Параметры:
    - vessel_data: базовый словарь судна из списка.

    Возвращает:
    - True при успешной записи, иначе False.
    """
    try:
        # Небольшая случайная задержка для предотвращения одновременных запросов
        time.sleep(random.uniform(0.5, 1.5))

        # Если есть URL страницы деталей, загрузить и распарсить
        if vessel_data.get("url"):
            with cache_lock:
                detail_html = detail_cache.get(vessel_data["url"])
            if detail_html is None:
                detail_html = fetch_page(vessel_data["url"], metrics=metrics)
                with cache_lock:
                    detail_cache[vessel_data["url"]] = detail_html
            if detail_html:
                vessel_data = parse_vessel_detail_page(detail_html, vessel_data)

        if not validate_vessel_payload(vessel_data, metrics):
            metrics.invalid_payload += 1
            logging.warning(
                "Skipping vessel invalid payload name=%r mmsi=%r type=%r url=%s",
                vessel_data.get("name"),
                vessel_data.get("mmsi"),
                vessel_data.get("general_type"),
                vessel_data.get("url"),
            )
            return False

        if save_vessel(vessel_data):
            log_event(
                logging.getLogger(__name__),
                "vessel_saved",
                scraper="myshiptracking",
                mmsi=vessel_data.get("mmsi"),
                name=vessel_data.get("name"),
            )
            return True
    except Exception as e:
        logging.error(f"Error processing vessel {vessel_data.get('name')}: {e}")
    return False


def main():
    """Точка входа скрапера MyShipTracking.

    Управление режимом через ENV `SCRAPER_MODE`: "test" или "full".
    Использует сохранение состояния для продолжения работы с нужной страницы.

    Побочные эффекты:
    - HTTP-запросы к myshiptracking.com;
    - запись карточек судов и состояния в PostgreSQL;
    - сохранение фотографий в локальное хранилище.
    """
    mode = os.getenv("SCRAPER_MODE", "test")
    metrics = RuntimeMetrics()
    logging.info(f"MyShipTracking Scraper started, mode: {mode}")
    preflight_conn = get_db_conn()
    try:
        validate_scraper_schema(preflight_conn)
    finally:
        preflight_conn.close()

    # Загрузить состояние
    start_page, vessels_processed = get_scraper_state(mode)

    # Определить лимиты
    if mode == "test":
        max_vessels = config.MAX_VESSELS_TEST
        logging.info(f"Test mode: max {max_vessels} vessels")
    else:
        max_vessels = config.MAX_VESSELS_FULL
        logging.info("Full mode: unlimited vessels")

    max_pages = config.MAX_PAGES
    if max_pages:
        logging.info(f"Max pages: {max_pages}")
    else:
        logging.info("Max pages: unlimited")

    logging.info(
        f"Starting from page {start_page}, vessels processed: {vessels_processed}"
    )

    current_page = start_page
    total_saved = 0
    consecutive_404s = 0  # Счётчик последовательных 404 ошибок
    MAX_CONSECUTIVE_404S = 10  # Остановиться после 10 подряд 404

    # Количество параллельных потоков
    detail_cache = {}
    detail_cache_lock = threading.Lock()
    last_page_error_ratio = 0.0
    retry_count_before_page = metrics.retry_count
    checkpoint_every_saved = 10

    try:
        while True:
            # Проверить лимиты
            if max_vessels and vessels_processed >= max_vessels:
                logging.info(f"Reached vessel limit: {max_vessels}")
                break

            if max_pages and current_page > max_pages:
                logging.info(f"Reached page limit: {max_pages}")
                break

            # Остановиться если слишком много 404 подряд
            if consecutive_404s >= MAX_CONSECUTIVE_404S:
                logging.info(
                    f"Stopping: {consecutive_404s} consecutive 404 errors, likely reached end of data"
                )
                break

            # Построить URL для текущей страницы
            if current_page == 1:
                url = f"{config.BASE_URL}?ajax=true&pp={config.VESSELS_PER_PAGE}"
            else:
                url = f"{config.BASE_URL}?ajax=true&pp={config.VESSELS_PER_PAGE}&page={current_page}"

            logging.info(f"Fetching page {current_page}: {url}")

            # Загрузить и распарсить страницу списка
            html = fetch_page(url, metrics=metrics)
            if html == "404_NOT_FOUND":
                consecutive_404s += 1
                metrics.pages_failed += 1
                logging.warning(
                    f"Page {current_page} not found (404), skipping to next page ({consecutive_404s}/{MAX_CONSECUTIVE_404S} consecutive)"
                )
                current_page += 1
                continue
            if not html:
                logging.error(f"Failed to fetch page {current_page}")
                metrics.pages_failed += 1
                break

            # Сбросить счётчик 404 при успешной загрузке
            consecutive_404s = 0

            vessels = parse_vessel_list_page(html)
            metrics.pages_ok += 1
            log_event(
                logging.getLogger(__name__),
                "page_processed",
                scraper="myshiptracking",
                page=current_page,
                vessels_found=len(vessels),
            )
            if not vessels:
                logging.info("No more vessels found")
                break

            workers = choose_worker_count(
                last_page_error_ratio=last_page_error_ratio,
                recent_retry_count=max(metrics.retry_count - retry_count_before_page, 0),
            )
            logging.info(
                f"Found {len(vessels)} vessels on page {current_page}. Processing with {workers} threads..."
            )

            # Обработать суда параллельно
            page_processed = 0
            page_saved = 0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = []
                for vessel_data in vessels:
                    if max_vessels and vessels_processed >= max_vessels:
                        break
                    futures.append(
                        executor.submit(process_vessel, vessel_data, metrics, detail_cache, detail_cache_lock)
                    )

                for future in as_completed(futures):
                    result = False
                    try:
                        result = bool(future.result())
                    except Exception as exc:
                        logging.error(f"Worker error on page {current_page}: {exc}")
                    metrics.vessels_parsed += 1
                    page_processed += 1
                    if result:
                        total_saved += 1
                        page_saved += 1
                        vessels_processed += 1
                        metrics.vessels_saved += 1
                        if total_saved % checkpoint_every_saved == 0:
                            save_scraper_state(mode, current_page, vessels_processed)

            if page_processed:
                last_page_error_ratio = max(
                    0.0, min(1.0, (page_processed - page_saved) / float(page_processed))
                )
            retry_count_before_page = metrics.retry_count

            # Сохранить состояние после каждой страницы
            save_scraper_state(mode, current_page, vessels_processed)
            if last_page_error_ratio > 0.5:
                logging.warning(
                    "Quality guardrail: high error ratio page=%s ratio=%.2f",
                    current_page,
                    last_page_error_ratio,
                )
            if metrics.http_failures > 20:
                logging.warning(
                    "Quality guardrail: many final HTTP failures count=%s",
                    metrics.http_failures,
                )
            current_page += 1

            # Периодический перерыв для избежания обнаружения
            if current_page % config.BREAK_AFTER_PAGES == 0:
                break_time = random.uniform(
                    config.BREAK_DURATION_MIN, config.BREAK_DURATION_MAX
                )
                logging.info(
                    f"Taking a break for {break_time:.0f} seconds after {config.BREAK_AFTER_PAGES} pages..."
                )
                time.sleep(break_time)

            # Задержка между страницами
            delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
            time.sleep(delay)

    except KeyboardInterrupt:
        logging.info("Interrupted by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    finally:
        save_scraper_state(mode, current_page, vessels_processed)
        logging.info(
            f"Scraper finished. Total saved: {total_saved}, total processed: {vessels_processed}"
        )
        logging.info(f"Runtime metrics: {metrics.snapshot()}")


if __name__ == "__main__":
    main()
