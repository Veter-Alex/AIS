"""
Скрапер VesselFinder.

Описание:
- Собирает список судов и детальные страницы с характеристиками.
- Загрузка HTML через requests (как MarineTraffic / MyShipTracking) и разбор BeautifulSoup.
- Сохраняет результаты в PostgreSQL с upsert-логикой и учётом источника.
- Поддерживает возобновление через таблицу состояния `scraper_state`.

Стиль:
- Комментарии и docstring на русском языке;
- поясняем архитектурные решения (паузы, ретраи, state), а не очевидный синтаксис.
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
import requests
from bs4 import BeautifulSoup
from common.db import (
    get_db_conn,
    load_scraper_state,
)
from common.db import (
    save_scraper_state as persist_scraper_state,
)
from common.http import fetch_page_with_retry
from common.logging_setup import configure_scraper_logging
from common.logging_utils import log_event
from common.metrics import RuntimeMetrics
from common.normalize import parse_int
from common.schema import validate_scraper_schema
from common.upsert import source_priority_sql
from PIL import Image

configure_scraper_logging("vesselfinder")

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


def extract_metric_value(text, labels):
    """Извлечь числовое значение рядом с одним из ярлыков метрики."""
    if not text:
        return None
    for label in labels:
        pattern = (
            rf"{label}\s*(?:\([^)]*\))?\s*[:\-]?\s*([0-9][0-9.,\s]{{0,15}})"
        )
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        digits = re.sub(r"\D", "", m.group(1))
        if not digits:
            continue
        return digits
    return None


def choose_worker_count(
    last_page_error_ratio: float, recent_retry_count: int
) -> int:
    if last_page_error_ratio > 0.65 or recent_retry_count >= 20:
        workers = 1
    elif last_page_error_ratio > 0.4 or recent_retry_count >= 12:
        workers = 2
    elif last_page_error_ratio < 0.2 and recent_retry_count <= 2:
        workers = 3
    else:
        workers = 2
    # Верхний предел потоков можно принудительно зажать через ENV для "мягкого" режима.
    max_workers_env = os.getenv("SOFT_MAX_WORKERS")
    if max_workers_env:
        try:
            hard_cap = max(1, int(max_workers_env))
            workers = min(workers, hard_cap)
        except ValueError:
            logging.warning(
                "SOFT_MAX_WORKERS=%r не распознан, используем авто-режим",
                max_workers_env,
            )
    return workers


def validate_vessel_payload(vessel_data, metrics):
    vessel_data["name"] = normalize_vessel_name(vessel_data.get("name"))
    vessel_data["flag"] = normalize_label_text(vessel_data.get("flag"))
    vessel_data["general_type"] = normalize_label_text(
        vessel_data.get("general_type")
    )
    vessel_data["detailed_type"] = normalize_label_text(
        vessel_data.get("detailed_type")
    )
    vessel_data["mmsi"] = normalize_mmsi(vessel_data.get("mmsi"))

    if not vessel_data.get("name"):
        metrics.empty_name += 1
        return False
    if not vessel_data.get("mmsi"):
        metrics.invalid_mmsi += 1
        return False

    vessel_data["year_built"] = sanitize_numeric(
        vessel_data.get("year_built"),
        min_value=1800,
        max_value=datetime.now().year + 1,
    )
    vessel_data["length"] = sanitize_numeric(
        vessel_data.get("length"), min_value=10, max_value=500
    )
    vessel_data["width"] = sanitize_numeric(
        vessel_data.get("width"), min_value=2, max_value=90
    )
    vessel_data["gt"] = sanitize_numeric(
        vessel_data.get("gt"), min_value=50, max_value=600000
    )
    vessel_data["dwt"] = sanitize_numeric(
        vessel_data.get("dwt"), min_value=100, max_value=700000
    )
    return True


def get_scraper_state(mode):
    """Получить сохраненное состояние скрапера для заданного режима.

    Параметры:
    - mode: строка режима (`test` или `full`).

    Возвращает:
    - кортеж `(last_page, vessels_count)`;
    - `(1, 0)`, если состояние для режима отсутствует.
    """
    conn = get_db_conn(
        config.DB_NAME,
        config.DB_USER,
        config.DB_PASSWORD,
        config.DB_HOST,
        config.DB_PORT,
    )
    try:
        last_page, vessels_count = load_scraper_state(
            conn, "vesselfinder", mode
        )
        if last_page != 1 or vessels_count != 0:
            logging.info(
                f"Загружено состояние для режима '{mode}': страница {last_page}, судов {vessels_count}"
            )
            return last_page, vessels_count
        logging.info(
            f"Состояние для режима '{mode}' не найдено, начинаем с начала"
        )
        return 1, 0
    finally:
        conn.close()


def save_scraper_state(mode, last_page, vessels_count):
    """Сохранить текущее состояние скрапера в таблицу `scraper_state`.

    Параметры:
    - mode: активный режим запуска;
    - last_page: следующая/последняя обработанная страница;
    - vessels_count: общее число обработанных судов.

    Побочные эффекты:
    - выполняет upsert и commit в БД.
    """
    conn = get_db_conn(
        config.DB_NAME,
        config.DB_USER,
        config.DB_PASSWORD,
        config.DB_HOST,
        config.DB_PORT,
    )
    try:
        persist_scraper_state(
            conn, "vesselfinder", mode, last_page, vessels_count
        )
        logging.info(
            f"Состояние сохранено: режим '{mode}', страница {last_page}, судов {vessels_count}"
        )
    finally:
        conn.close()


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
        r = requests.get(photo_url, timeout=config.PHOTO_DOWNLOAD_TIMEOUT)
        if r.status_code == 200:
            # Открыть изображение в памяти
            img = Image.open(io.BytesIO(r.content))

            # Конвертировать в RGB (для JPEG)
            if img.mode in ("RGBA", "LA", "P"):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                rgb_img.paste(
                    img, mask=img.split()[-1] if img.mode == "RGBA" else None
                )
                img = rgb_img

            # Сжать размер (макс 320x240)
            img.thumbnail((320, 240), Image.Resampling.LANCZOS)

            # Сохранить с качеством 65% (экономия ~70% размера)
            img.save(dest, "JPEG", quality=65, optimize=True)
            logging.info(f"Фото сохранено: {dest}")
            return dest
        logging.warning(f"Фото не скачано status={r.status_code}")
        return None
    except Exception as e:
        logging.warning(f"Ошибка скачивания/сжатия фото: {e}")
        return None


def save_to_db(vessel):
    """Сохранить карточку судна в БД (upsert по MMSI).

    Параметры:
    - vessel: словарь с полями судна после парсинга страницы деталей.

    Поведение:
    - если MMSI отсутствует, запись пропускается;
    - обновление учитывает приоритет источников из таблицы `source_priority`;
    - поля обновляются через COALESCE, чтобы не перетирать валидные данные пустыми.

    Побочные эффекты:
    - выполняет commit транзакции;
    - пишет подробные события в лог.
    """
    conn = get_db_conn(
        config.DB_NAME,
        config.DB_USER,
        config.DB_PASSWORD,
        config.DB_HOST,
        config.DB_PORT,
    )
    cur = conn.cursor()
    imo = vessel.get("imo")
    mmsi = vessel.get("mmsi")
    logging.info(
        f"save_to_db: name={vessel.get('name')} imo={imo} mmsi={mmsi}"
    )
    if not mmsi:
        logging.warning("Пропуск записи: нет MMSI")
        cur.close()
        conn.close()
        return

    incoming_prio = source_priority_sql("%s")
    existing_prio = source_priority_sql("vessels.info_source")
    sql = f"""
    INSERT INTO vessels (
        name, imo, mmsi, call_sign, general_type, detailed_type, flag, year_built, length, width, dwt, gt, home_port, photo_url, photo_path, description, info_source, updated_at, vessel_key
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s)
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
            WHEN {existing_prio} <= {incoming_prio}
            THEN vessels.info_source
            ELSE %s
        END,
        updated_at=NOW(),
        vessel_key=COALESCE(EXCLUDED.vessel_key, vessels.vessel_key);
    """
    source_name = "vesselfinder.com"
    try:
        cur.execute(
            sql,
            (
                (vessel.get("name") or "").strip() or None,
                imo,
                mmsi,
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
                source_name,  # info_source в INSERT
                vessel.get("vessel_key"),
                source_name,  # info_source для CASE WHEN в UPDATE
                source_name,
            ),
        )
        conn.commit()
        logging.info(f"UPSERT выполнен: mmsi={mmsi}")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def fetch_page(url, metrics=None):
    """Загрузить HTML страницы с повторными попытками (общий паттерн скраперов AIS)."""

    def _on_retry(_url, _attempt, _max_attempts, _kind):
        if metrics is not None:
            metrics.retry_count += 1

    page_html = fetch_page_with_retry(
        session=session,
        url=url,
        user_agents=config.USER_AGENTS,
        timeout=30,
        max_retries=config.MAX_RETRIES,
        retry_delay_range=(config.RETRY_DELAY_MIN, config.RETRY_DELAY_MAX),
        return_404_marker=True,
        on_retry=_on_retry,
    )
    if page_html is None and metrics is not None:
        metrics.http_failures += 1
    return page_html


def get_vessel_links(page=1, vessel_type=None):
    """Получить список ссылок на карточки судов со страницы каталога.

    Параметры:
    - page: номер страницы пагинации;
    - vessel_type: код типа судна для серверного фильтра (опционально).

    Возвращает:
    - кортеж (links, fetch_failed):
      * links: список абсолютных URL вида `/vessels/details/...`;
      * fetch_failed=True, если страницу не удалось загрузить из-за сетевой ошибки.
    """
    if vessel_type:
        if page == 1:
            url = f"https://www.vesselfinder.com/vessels?type={vessel_type}"
        else:
            url = f"https://www.vesselfinder.com/vessels?page={page}&type={vessel_type}"
    else:
        url = f"https://www.vesselfinder.com/vessels?page={page}"
    html = fetch_page(url, metrics=getattr(config, "_runtime_metrics", None))
    if not html:
        return [], True
    if html == "404_NOT_FOUND":
        return [], False
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("table a[href^='/vessels/details/']"):
        href = a.get("href")
        if href:
            links.append("https://www.vesselfinder.com" + href)
    return links, False


def parse_vessel(url):
    """Распарсить детальную страницу судна и собрать нормализованную запись.

    Параметры:
    - url: абсолютный URL карточки судна.

    Возвращает:
    - словарь с полями судна (`imo`, `mmsi`, `name`, размеры, тоннаж, фото и т.д.);
    - None при фатальной ошибке после всех попыток.

    Особенности:
    - применяет несколько fallback-regex для устойчивости к изменениям DOM;
    - аккуратно парсит DWT, чтобы избежать ложных значений;
    - при наличии фото скачивает и сохраняет локальный путь.
    """
    html = fetch_page(url, metrics=getattr(config, "_runtime_metrics", None))
    if not html or html == "404_NOT_FOUND":
        logging.error(f"Не удалось загрузить страницу: {url}")
        return None
    soup = BeautifulSoup(html, "html.parser")
    vessel = {}
    vessel["info_source"] = "vesselfinder.com"
    vessel["updated_at"] = datetime.utcnow()
    h1 = soup.find("h1")
    vessel["name"] = normalize_vessel_name(
        " ".join(h1.text.split()) if h1 and h1.text else None
    )

    tables = soup.find_all(
        "table", class_=lambda c: c and ("tpt1" in c or "aparams" in c)
    )
    combined = " ".join(t.get_text(" ", strip=True) for t in tables)

    def rx(pattern, flags=0, group=1, _text=combined):
        m = re.search(pattern, _text, flags)
        return m.group(group) if m else None

    vessel["imo"] = rx(r"IMO\s*(\d{7})") or rx(r"IMO number\s*(\d{7})")
    vessel["mmsi"] = normalize_mmsi(rx(r"MMSI\s*(\d{9})"))
    vessel["call_sign"] = rx(r"Callsign\s*([A-Z0-9]+)")
    vessel["flag"] = normalize_label_text(
        rx(
            r"Флаг\s+([A-Za-z (),\-]+?)(?:\s+Год постройки|\s+Флаг AIS|\n)",
            flags=re.IGNORECASE,
        )
        or rx(
            r"Flag\s+([A-Za-z (),\-]+?)(?:\s+Year of Build|\s+AIS Flag|\n)",
            flags=re.IGNORECASE,
        )
        or rx(
            r"Флаг AIS\s+([A-Za-z (),\-]+?)(?:\n|$)", flags=re.IGNORECASE
        )
        or rx(
            r"AIS Flag\s+([A-Za-z (),\-]+?)(?:\n|$)", flags=re.IGNORECASE
        )
    )
    vessel["year_built"] = (
        rx(r"Year of Build\s*(\d{4})")
        or rx(r"Built\s*(\d{4})")
        or rx(r"Год постройки\s*(\d{4})")
    )
    vessel["general_type"] = normalize_label_text(
        rx(r"Ship Type\s*([A-Za-z /-]+?)\s+Flag")
        or rx(r"is a\s+([A-Za-z /-]+?)\s+built", flags=re.IGNORECASE)
    )
    vessel["detailed_type"] = vessel.get("general_type")
    vessel["length"] = rx(r"Length Overall \(m\)\s*([0-9.]+)")
    vessel["width"] = rx(r"Beam \(m\)\s*([0-9.]+)")
    vessel["gt"] = rx(r"Gross Tonnage\s*(\d+)")

    # DWT: осторожный парсинг — значение может отсутствовать и быть заменено '-'
    def extract_dwt(text: str):
        seg = re.search(r"Deadweight \(t\)[^A-Za-z0-9]*([\d,]{2,})", text)
        if seg:
            raw = seg.group(1)
            # Отбрасываем слишком короткие (1 цифра) и явно некорректные значения
            digits = re.sub(r"[^0-9]", "", raw)
            if len(digits) >= 3:  # реальный DWT обычно >= 100
                return digits
        return None

    vessel["dwt"] = extract_dwt(combined)
    vessel["home_port"] = rx(r"Home Port\s*([A-Za-z0-9 -]+)")

    page_text = soup.get_text(" ", strip=True)
    if not vessel.get("imo"):
        m = re.search(r"IMO\s*(\d{7})", page_text)
        if m:
            vessel["imo"] = m.group(1)
    if not vessel.get("mmsi"):
        m = re.search(r"MMSI\s*(\d{9})", page_text)
        if m:
            vessel["mmsi"] = normalize_mmsi(m.group(1))

    logging.info(
        f"RAW metrics: length_raw={vessel.get('length')} width_raw={vessel.get('width')} gt_raw={vessel.get('gt')} dwt_raw={vessel.get('dwt')} year_raw={vessel.get('year_built')}"
    )
    # Более толерантные regex если предыдущие не сработали
    if not vessel.get("length"):
        vessel["length"] = rx(r"Length Overall[^0-9]*([0-9]+\.[0-9]+)")
    if not vessel.get("width"):
        vessel["width"] = rx(r"Beam[^0-9]*([0-9]+\.[0-9]+)")
    if not vessel.get("gt"):
        vessel["gt"] = rx(r"Gross Tonnage[^0-9]*(\d+)")
    if not vessel.get("length"):
        vessel["length"] = extract_metric_value(
            page_text,
            labels=[r"Length Overall", r"\bLOA\b", r"\bLength\b"],
        )
    if not vessel.get("gt"):
        vessel["gt"] = extract_metric_value(
            page_text,
            labels=[r"Gross Tonnage", r"\bGT\b"],
        )
    if not vessel.get("dwt"):
        vessel["dwt"] = extract_metric_value(
            page_text,
            labels=[r"Deadweight", r"\bDWT\b", r"Dead Weight"],
        )
    # Не используем fallback на одиночную цифру после Deadweight, чтобы избежать ложных '3'

    vessel["year_built"] = sanitize_numeric(
        vessel.get("year_built"),
        min_value=1800,
        max_value=datetime.now().year + 1,
    )
    vessel["length"] = sanitize_numeric(
        vessel.get("length"), min_value=10, max_value=500
    )
    vessel["width"] = sanitize_numeric(
        vessel.get("width"), min_value=2, max_value=90
    )
    vessel["dwt"] = sanitize_numeric(
        vessel.get("dwt"), min_value=100, max_value=700000
    )
    vessel["gt"] = sanitize_numeric(
        vessel.get("gt"), min_value=50, max_value=600000
    )

    img = soup.find("img", class_="main-photo")
    vessel["photo_url"] = img["src"] if img and img.get("src") else None
    vessel_key = vessel.get("imo") or vessel.get("mmsi")
    if vessel["photo_url"] and vessel_key:
        vessel["photo_path"] = download_image(
            vessel["photo_url"], vessel_key
        )
    logging.info(
        f"Парсинг судна завершён: name={vessel.get('name')} imo={vessel.get('imo')} mmsi={vessel.get('mmsi')}"
    )
    return vessel


def main():
    """Точка входа скрапера VesselFinder.

    Сценарий:
    1) определяет режим (`test`/`full`) и лимиты;
    2) восстанавливает прогресс из `scraper_state`;
    3) обходит страницы каталога и карточки судов;
    4) сохраняет результат в БД и периодически фиксирует состояние.

    Побочные эффекты:
    - сетевые запросы к VesselFinder;
    - запись в PostgreSQL;
    - сохранение изображений на диск.
    """
    mode = os.getenv("SCRAPER_MODE", "test")
    metrics = RuntimeMetrics()
    config._runtime_metrics = metrics
    logging.info(f"main() started, режим: {mode}")
    schema_conn = get_db_conn(
        config.DB_NAME,
        config.DB_USER,
        config.DB_PASSWORD,
        config.DB_HOST,
        config.DB_PORT,
    )
    try:
        validate_scraper_schema(schema_conn)
    finally:
        schema_conn.close()

    # Загружаем сохраненное состояние
    start_page, saved_count = get_scraper_state(mode)

    # Определяем лимиты в зависимости от режима
    if mode == "test":
        max_vessels = config.MAX_VESSELS_TEST
        max_pages = 3  # В тестовом режиме ограничиваем страницы
    else:  # "full"
        max_vessels = config.MAX_VESSELS_FULL
        max_pages = config.MAX_PAGES

    logging.info(
        f"Лимит судов: {max_vessels if max_vessels else 'без ограничений'}"
    )
    logging.info(
        f"Лимит страниц: {max_pages if max_pages else 'без ограничений'}"
    )

    count = saved_count
    page = start_page
    detail_cache = {}
    cache_lock = threading.Lock()
    last_page_error_ratio = 0.0
    retry_count_before_page = metrics.retry_count
    checkpoint_every_saved = 10
    detail_delay_multiplier = float(
        os.getenv("DETAIL_DELAY_MULTIPLIER", "1.0")
    )
    break_duration_multiplier = float(
        os.getenv("BREAK_DURATION_MULTIPLIER", "1.0")
    )
    failure_streak_limit = int(os.getenv("FAILURE_STREAK_LIMIT", "3"))
    failure_cooldown_seconds = int(
        os.getenv("FAILURE_COOLDOWN_SECONDS", "900")
    )
    consecutive_fetch_failures = 0
    vessel_type = (
        int(os.getenv("VESSEL_TYPE", config.VESSEL_TYPE))
        if os.getenv("VESSEL_TYPE") or config.VESSEL_TYPE
        else None
    )
    logging.info(f"Начинаем с страницы {page}, уже обработано судов: {count}")
    if vessel_type:
        logging.info(f"Фильтр по типу судов: {vessel_type}")

    try:
        while True:
            # Проверка лимита страниц
            if max_pages and page > max_pages:
                logging.info(f"Достигнут лимит страниц: {max_pages}")
                save_scraper_state(mode, page, count)
                break

            logging.info(f"Парсинг страницы {page}")
            links, fetch_failed = get_vessel_links(page, vessel_type)

            if not links:
                if fetch_failed:
                    consecutive_fetch_failures += 1
                    logging.warning(
                        "Не удалось загрузить список судов page=%s (streak=%s/%s)",
                        page,
                        consecutive_fetch_failures,
                        failure_streak_limit,
                    )
                    if consecutive_fetch_failures >= failure_streak_limit:
                        logging.warning(
                            "Активируем cooldown на %s сек из-за серии сетевых сбоев",
                            failure_cooldown_seconds,
                        )
                        save_scraper_state(mode, page, count)
                        time.sleep(max(0, failure_cooldown_seconds))
                        consecutive_fetch_failures = 0
                    continue
                logging.info("Нет больше судов для парсинга")
                save_scraper_state(mode, page, count)
                break
            consecutive_fetch_failures = 0
            metrics.pages_ok += 1
            log_event(
                logging.getLogger(__name__),
                "page_processed",
                scraper="vesselfinder",
                page=page,
                vessels_found=len(links),
            )

            workers = choose_worker_count(
                last_page_error_ratio=last_page_error_ratio,
                recent_retry_count=max(
                    metrics.retry_count - retry_count_before_page, 0
                ),
            )
            logging.info(
                "Обработка страницы %s с %s потоками (prev_error_ratio=%.2f)",
                page,
                workers,
                last_page_error_ratio,
            )
            page_processed = 0
            page_saved = 0
            future_to_link = {}
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for link in links:
                    if max_vessels and count >= max_vessels:
                        break
                    with cache_lock:
                        cached = detail_cache.get(link)
                    if cached is not None:
                        future = pool.submit(lambda value=cached: value)
                    else:
                        future = pool.submit(parse_vessel, link)
                    future_to_link[future] = link

                for future in as_completed(future_to_link):
                    link = future_to_link[future]
                    if max_vessels and count >= max_vessels:
                        break
                    logging.info(f"Парсинг судна: {link}")
                    vessel = None
                    try:
                        vessel = future.result()
                    except Exception as exc:
                        logging.error(f"Ошибка обработки судна {link}: {exc}")
                    page_processed += 1
                    metrics.vessels_parsed += 1
                    if not vessel:
                        continue

                    if not validate_vessel_payload(vessel, metrics):
                        metrics.invalid_payload += 1
                        logging.warning(
                            "Пропуск судна: не пройден payload-контракт name=%r mmsi=%r url=%s",
                            vessel.get("name"),
                            vessel.get("mmsi"),
                            link,
                        )
                        continue

                    with cache_lock:
                        detail_cache[link] = vessel
                    save_to_db(vessel)
                    count += 1
                    page_saved += 1
                    metrics.vessels_saved += 1
                    log_event(
                        logging.getLogger(__name__),
                        "vessel_saved",
                        scraper="vesselfinder",
                        mmsi=vessel.get("mmsi"),
                        name=vessel.get("name"),
                    )
                    if count % checkpoint_every_saved == 0:
                        save_scraper_state(mode, page, count)

            if page_processed > 0:
                last_page_error_ratio = max(
                    0.0,
                    min(
                        1.0,
                        (page_processed - page_saved) / float(page_processed),
                    ),
                )
            retry_count_before_page = metrics.retry_count

            if last_page_error_ratio > 0.5:
                logging.warning(
                    "Quality guardrail: высокий error ratio page=%s ratio=%.2f",
                    page,
                    last_page_error_ratio,
                )
            if metrics.http_failures > 20:
                logging.warning(
                    "Quality guardrail: много финальных HTTP-фейлов count=%s",
                    metrics.http_failures,
                )

            if max_vessels and count >= max_vessels:
                logging.info(f"Достигнут лимит судов: {max_vessels}")
                save_scraper_state(mode, page, count)
                logging.info("main() finished")
                return

            delay = random.uniform(
                config.DETAIL_DELAY_MIN, config.DETAIL_DELAY_MAX
            )
            delay = max(0.0, delay * detail_delay_multiplier)
            logging.info(f"Задержка {delay:.1f} сек")
            time.sleep(delay)

            # Сохраняем состояние после каждой страницы
            save_scraper_state(mode, page + 1, count)
            page += 1

            # Периодический перерыв для снижения риска блокировки
            if page % config.BREAK_AFTER_PAGES == 0:
                break_time = random.uniform(
                    config.BREAK_DURATION_MIN, config.BREAK_DURATION_MAX
                )
                break_time = max(
                    0.0, break_time * break_duration_multiplier
                )
                logging.info(
                    f"Перерыв {break_time:.0f} сек после {config.BREAK_AFTER_PAGES} страниц..."
                )
                time.sleep(break_time)
    except Exception as exc:
        logging.error(f"Критическая ошибка main(): {exc}")
        metrics.pages_failed += 1
        raise
    finally:
        save_scraper_state(mode, page, count)
        logging.info(f"main() finished, обработано судов: {count}")
        logging.info(f"Runtime metrics: {metrics.snapshot()}")


if __name__ == "__main__":
    main()
