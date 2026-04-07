"""
Скрапер MarineTraffic.

Описание:
- Загружает списки судов со страниц пагинации (250,428+ судов).
- Извлекает базовые поля: имя, MMSI, IMO, тип, флаг.
- Переходит на страницу судна для получения детальной информации (длина, ширина, GT, DWT, год постройки).
- Скачивает фотографии судов с компрессией.
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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import config
import psycopg2
import requests
from bs4 import BeautifulSoup
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Глобальная сессия для переиспользования соединений
session = requests.Session()


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

    file_name = f"{vessel_key}.jpg"
    file_path = os.path.join(image_dir, file_name)

    try:
        headers = {"User-Agent": random.choice(config.USER_AGENTS)}
        response = session.get(photo_url, headers=headers, timeout=30)
        response.raise_for_status()

        # Открыть изображение в памяти
        img = Image.open(io.BytesIO(response.content))

        # Конвертация RGBA в RGB для JPEG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Сжатие до 320x240
        img.thumbnail((320, 240), Image.Resampling.LANCZOS)

        # Сохранить с качеством 65%
        img.save(file_path, "JPEG", quality=65, optimize=True)

        return file_path
    except Exception as e:
        logging.warning(f"Failed to download image from {photo_url}: {e}")
        return None


def fetch_page(url, retries=0):
    """Загрузить HTML страницы с повторными попытками.

    Параметры:
    - url: URL страницы.
    - retries: текущий счётчик попыток.

    Возвращает:
    - HTML текст или None в случае фатальной ошибки, "404_NOT_FOUND" при 404.
    """
    headers = {"User-Agent": random.choice(config.USER_AGENTS)}

    try:
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return "404_NOT_FOUND"
        logging.warning(f"HTTP error fetching {url}: {e}")
        if retries < config.MAX_RETRIES:
            delay = random.uniform(config.RETRY_DELAY_MIN, config.RETRY_DELAY_MAX)
            logging.info(
                f"Retrying in {delay:.1f}s... (attempt {retries + 1}/{config.MAX_RETRIES})"
            )
            time.sleep(delay)
            return fetch_page(url, retries + 1)
        return None
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        if retries < config.MAX_RETRIES:
            delay = random.uniform(config.RETRY_DELAY_MIN, config.RETRY_DELAY_MAX)
            logging.info(
                f"Retrying in {delay:.1f}s... (attempt {retries + 1}/{config.MAX_RETRIES})"
            )
            time.sleep(delay)
            return fetch_page(url, retries + 1)
        return None


def parse_vessel_list_page(html):
    """Распарсить страницу со списком судов.

    Параметры:
    - html: HTML код страницы.

    Возвращает:
    - Список словарей с базовой информацией о судах: name, flag, general_type, detail_url.
    """
    soup = BeautifulSoup(html, "html.parser")
    vessels = []

    # Найти таблицу с судами
    table = soup.find("table")
    if not table:
        return vessels

    rows = table.find_all("tr")[1:]  # Пропустить заголовок

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        try:
            # Флаг (первая колонка - изображение флага, alt содержит название страны)
            flag_img = cols[0].find("img")
            flag = flag_img.get("alt", "Unknown").strip() if flag_img else "Unknown"

            # Название судна (вторая колонка - ссылка)
            name_link = cols[1].find("a")
            if not name_link:
                continue

            name = name_link.get_text(strip=True)
            detail_url = name_link.get("href", "")

            if detail_url and not detail_url.startswith("http"):
                detail_url = f"https://www.marinetraffic.org{detail_url}"

            # Тип судна (третья колонка текст, может быть после имени)
            # На MarineTraffic структура: Name | Service Status | Map/Info
            # Нужно найти тип из detail_url или текста
            general_type = "Unknown"
            vessel_type_text = cols[1].get_text(strip=True)
            # Попробуем извлечь тип из текста после имени
            if len(cols) >= 2:
                type_match = re.search(
                    r"(Container Ship|Bulk Carrier|Tanker|Cargo|Passenger|Cruise|Tug|Offshore|Fishing|Military|Yacht)",
                    vessel_type_text,
                    re.IGNORECASE,
                )
                if type_match:
                    general_type = type_match.group(1)

            vessels.append(
                {
                    "name": name,
                    "flag": flag,
                    "general_type": general_type,
                    "detail_url": detail_url,
                }
            )
        except Exception as e:
            logging.warning(f"Error parsing vessel row: {e}")
            continue

    return vessels


def parse_vessel_detail_page(html):
    """Распарсить страницу с детальной информацией о судне.

    Параметры:
    - html: HTML код страницы судна.

    Возвращает:
    - Словарь с полями: mmsi, imo, name, flag, general_type, built, length_m, beam_m, gross_tonnage, deadweight, photo_url.
    """
    soup = BeautifulSoup(html, "html.parser")
    data = {
        "mmsi": None,
        "imo": None,
        "name": None,
        "flag": None,
        "general_type": None,
        "year_built": None,
        "length": None,
        "width": None,
        "gt": None,
        "dwt": None,
        "photo_url": None,
    }

    try:
        # Извлечь данные из заголовка страницы (Name, Type, IMO)
        title_h1 = soup.find("h1")
        if title_h1:
            title_text = title_h1.get_text(strip=True)
            # Формат: "MSC MARIELLA Container Ship, IMO 9934747"
            match = re.match(r"(.+?)\s+(.*?),\s*IMO\s+(\d+)", title_text)
            if match:
                data["name"] = match.group(1).strip()
                data["general_type"] = match.group(2).strip()
                data["imo"] = match.group(3).strip()

        # Извлечь данные из таблицы "VESSEL INFORMATION"
        vessel_info_table = None
        for table in soup.find_all("table"):
            if "VESSEL INFORMATION" in table.get_text():
                vessel_info_table = table
                break

        if vessel_info_table:
            rows = vessel_info_table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    label = cols[0].get_text(strip=True)
                    value = cols[1].get_text(strip=True)

                    if "MMSI" in label:
                        data["mmsi"] = value
                    elif "Flag" in label:
                        data["flag"] = value
                    elif "Built" in label:
                        # Извлечь только год
                        year_match = re.search(r"(\d{4})", value)
                        if year_match:
                            data["year_built"] = int(year_match.group(1))
                    elif "Length" in label:
                        # Формат: "399 m / 1309 ft"
                        meter_match = re.search(r"(\d+)\s*m", value)
                        if meter_match:
                            data["length"] = int(meter_match.group(1))
                    elif "Beam" in label:
                        # Формат: "60 m / 197 ft"
                        meter_match = re.search(r"(\d+)\s*m", value)
                        if meter_match:
                            data["width"] = int(meter_match.group(1))
                    elif "Gross Tonnage" in label:
                        # Убрать запятые, пробелы
                        gt_clean = re.sub(r"[^\d]", "", value)
                        if gt_clean:
                            data["gt"] = int(gt_clean)
                    elif "DWT" in label and "Summer" in label:
                        # Формат: "Summer DWT: 281456"
                        dwt_clean = re.sub(r"[^\d]", "", value)
                        if dwt_clean:
                            data["dwt"] = int(dwt_clean)

        # Попробовать найти фото судна
        # MarineTraffic может иметь изображение в <img> с определёнными классами
        photo_img = soup.find(
            "img", {"class": re.compile(r"ship.*photo|vessel.*image", re.IGNORECASE)}
        )
        if not photo_img:
            # Альтернативный поиск: изображение с src содержащим "photos" или "vessels"
            photo_img = soup.find(
                "img", {"src": re.compile(r"(photos|vessels|ships)", re.IGNORECASE)}
            )

        if photo_img and photo_img.get("src"):
            photo_url = photo_img.get("src")
            if photo_url and not photo_url.startswith("http"):
                photo_url = f"https://www.marinetraffic.org{photo_url}"
            data["photo_url"] = photo_url

    except Exception as e:
        logging.warning(f"Error parsing vessel detail page: {e}")

    return data


def save_vessel_to_db(vessel_data, conn):
    """Сохранить информацию о судне в БД с умным upsert.

    Параметры:
    - vessel_data: словарь с данными судна.
    - conn: соединение с БД.

    Возвращает:
    - True если успешно, False иначе.
    """
    cursor = conn.cursor()

    try:
        # Обновляем только поля, где данных не было или приоритет источника выше
        cursor.execute(
            """
            INSERT INTO vessels (
                mmsi, imo, name, flag, general_type, year_built, 
                length, width, gt, dwt, photo_url, photo_path,
                info_source, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (mmsi) DO UPDATE SET
                imo = COALESCE(NULLIF(vessels.imo, ''), EXCLUDED.imo, vessels.imo),
                name = CASE
                    WHEN vessels.name IS NULL OR vessels.name = '' THEN EXCLUDED.name
                    WHEN (SELECT priority FROM source_priority WHERE source_name = EXCLUDED.info_source) < 
                         (SELECT priority FROM source_priority WHERE source_name = vessels.info_source) THEN EXCLUDED.name
                    ELSE vessels.name
                END,
                flag = CASE
                    WHEN vessels.flag IS NULL OR vessels.flag = '' THEN EXCLUDED.flag
                    WHEN (SELECT priority FROM source_priority WHERE source_name = EXCLUDED.info_source) < 
                         (SELECT priority FROM source_priority WHERE source_name = vessels.info_source) THEN EXCLUDED.flag
                    ELSE vessels.flag
                END,
                general_type = CASE
                    WHEN vessels.general_type IS NULL OR vessels.general_type = '' THEN EXCLUDED.general_type
                    WHEN (SELECT priority FROM source_priority WHERE source_name = EXCLUDED.info_source) < 
                         (SELECT priority FROM source_priority WHERE source_name = vessels.info_source) THEN EXCLUDED.general_type
                    ELSE vessels.general_type
                END,
                year_built = COALESCE(vessels.year_built, EXCLUDED.year_built),
                length = COALESCE(vessels.length, EXCLUDED.length),
                width = COALESCE(vessels.width, EXCLUDED.width),
                gt = COALESCE(vessels.gt, EXCLUDED.gt),
                dwt = COALESCE(vessels.dwt, EXCLUDED.dwt),
                photo_url = COALESCE(EXCLUDED.photo_url, vessels.photo_url),
                photo_path = COALESCE(EXCLUDED.photo_path, vessels.photo_path),
                info_source = CASE
                    WHEN (SELECT priority FROM source_priority WHERE source_name = EXCLUDED.info_source) <= 
                         (SELECT priority FROM source_priority WHERE source_name = vessels.info_source) THEN EXCLUDED.info_source
                    ELSE vessels.info_source
                END,
                updated_at = CASE
                    WHEN (SELECT priority FROM source_priority WHERE source_name = EXCLUDED.info_source) <= 
                         (SELECT priority FROM source_priority WHERE source_name = vessels.info_source) THEN EXCLUDED.updated_at
                    ELSE vessels.updated_at
                END
            """,
            (
                vessel_data.get("mmsi"),
                vessel_data.get("imo"),
                vessel_data.get("name"),
                vessel_data.get("flag"),
                vessel_data.get("general_type"),
                vessel_data.get("year_built"),
                vessel_data.get("length"),
                vessel_data.get("width"),
                vessel_data.get("gt"),
                vessel_data.get("dwt"),
                vessel_data.get("photo_url"),
                vessel_data.get("photo_path"),
                config.DATA_SOURCE,
                datetime.now(),
            ),
        )

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logging.error(
            f"Error saving vessel {vessel_data.get('name')} (MMSI: {vessel_data.get('mmsi')}): {e}"
        )
        return False
    finally:
        cursor.close()


def process_vessel(vessel_basic, conn):
    """Обработать одно судно: детали, фото и запись в БД.

    Параметры:
    - vessel_basic: словарь базовых данных из списка судов;
    - conn: активное подключение к PostgreSQL.

    Поведение:
    - делает паузу перед запросом detail-страницы;
    - объединяет базовые и детальные поля;
    - скачивает фото при наличии URL;
    - сохраняет запись через `save_vessel_to_db`.
    """
    detail_url = vessel_basic.get("detail_url")
    if not detail_url:
        return

    # Задержка перед запросом детальной страницы
    time.sleep(random.uniform(1.0, 3.0))

    html = fetch_page(detail_url)
    if not html or html == "404_NOT_FOUND":
        return

    vessel_data = parse_vessel_detail_page(html)

    # Дополнить данные из базового списка, если не извлечены со страницы детали
    if not vessel_data.get("name"):
        vessel_data["name"] = vessel_basic.get("name")
    if not vessel_data.get("flag"):
        vessel_data["flag"] = vessel_basic.get("flag")
    if not vessel_data.get("general_type"):
        vessel_data["general_type"] = vessel_basic.get("general_type")

    # Проверить наличие MMSI
    if not vessel_data.get("mmsi"):
        logging.warning(f"Vessel {vessel_data.get('name')} has no MMSI, skipping")
        return

    # Скачать фото, если есть
    photo_url = vessel_data.get("photo_url")
    if photo_url:
        mmsi = vessel_data.get("mmsi")
        photo_path = download_image(photo_url, mmsi)
        if photo_path:
            vessel_data["photo_path"] = photo_path
            logging.info(f"Photo saved: {photo_path}")
        else:
            logging.warning(f"Failed to download photo for {vessel_data.get('name')}")

    # Сохранить в БД
    if save_vessel_to_db(vessel_data, conn):
        logging.info(
            f"Saved vessel: {vessel_data.get('name')} (MMSI: {vessel_data.get('mmsi')})"
        )


def load_state(conn, mode):
    """Загрузить состояние скрапера из БД.

    Параметры:
    - conn: соединение с БД.
    - mode: режим работы ('test' или 'full').

    Возвращает:
    - Кортеж (last_page, vessels_count) или (0, 0) если состояние не найдено.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT last_page, vessels_count
        FROM scraper_state
        WHERE scraper_name = %s AND mode = %s
        """,
        (config.DATA_SOURCE, mode),
    )
    row = cursor.fetchone()
    cursor.close()

    if row:
        return row[0], row[1]
    return 0, 0


def save_state(conn, mode, page, vessels_count):
    """Сохранить состояние скрапера в БД.

    Параметры:
    - conn: соединение с БД.
    - mode: режим работы.
    - page: текущая страница.
    - vessels_count: количество обработанных судов.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scraper_state (scraper_name, mode, last_page, vessels_count, last_run_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (scraper_name, mode) DO UPDATE SET
            last_page = EXCLUDED.last_page,
            vessels_count = EXCLUDED.vessels_count,
            last_run_at = EXCLUDED.last_run_at
        """,
        (config.DATA_SOURCE, mode, page, vessels_count, datetime.now()),
    )
    conn.commit()
    cursor.close()
    logging.info(f"State saved: mode '{mode}', page {page}, vessels {vessels_count}")


def main():
    """Точка входа скрапера MarineTraffic.

    Сценарий:
    1) инициализирует подключение к БД и состояние прогресса;
    2) обходит страницы каталога с учетом лимитов и 404-стратегии;
    3) обрабатывает суда параллельно (ThreadPoolExecutor);
    4) сохраняет state после каждой страницы.

    Побочные эффекты:
    - сетевые запросы к marinetraffic.org;
    - запись данных и состояния в PostgreSQL;
    - сохранение изображений судов в файловую систему.
    """
    # Режим работы из переменной окружения
    mode = os.getenv("SCRAPER_MODE", "full").lower()

    logging.info(f"MarineTraffic Scraper started, mode: {mode}")

    # Подключение к БД
    conn = psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "vessels_db"),
        user=os.getenv("POSTGRES_USER", "user"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )

    # Загрузить состояние
    last_page, vessels_count = load_state(conn, mode)

    if last_page == 0:
        logging.info(f"No state found for mode '{mode}', starting from beginning")
        current_page = 1
        vessels_processed = 0
    else:
        logging.info(
            f"Loaded state for mode '{mode}': page {last_page}, vessels {vessels_count}"
        )
        current_page = last_page
        vessels_processed = vessels_count

    # Определить лимиты
    if mode == "test":
        max_vessels = config.MAX_VESSELS_TEST
        max_pages = config.MAX_PAGES
        logging.info(f"Test mode: max {max_vessels} vessels")
    else:
        max_vessels = config.MAX_VESSELS_FULL
        max_pages = config.MAX_PAGES
        logging.info("Full mode: unlimited vessels")

    if max_pages:
        logging.info(f"Max pages: {max_pages}")
    else:
        logging.info("Max pages: unlimited")

    logging.info(
        f"Starting from page {current_page}, vessels processed: {vessels_processed}"
    )

    total_saved = 0
    consecutive_404s = 0
    MAX_CONSECUTIVE_404S = 10

    try:
        while True:
            # Проверить лимиты
            if max_vessels and vessels_processed >= max_vessels:
                logging.info(f"Reached vessel limit: {max_vessels}")
                break

            if max_pages and current_page > max_pages:
                logging.info(f"Reached page limit: {max_pages}")
                break

            # Построить URL для текущей страницы
            url = f"{config.BASE_URL}?page={current_page}&status=Any%20Service%20Status"

            logging.info(f"Fetching page {current_page}: {url}")

            # Загрузить и распарсить страницу списка
            html = fetch_page(url)

            if html == "404_NOT_FOUND":
                consecutive_404s += 1
                logging.warning(
                    f"Page {current_page} not found (404), skipping to next page ({consecutive_404s}/{MAX_CONSECUTIVE_404S} consecutive)"
                )

                if consecutive_404s >= MAX_CONSECUTIVE_404S:
                    logging.info(
                        f"Stopping: {MAX_CONSECUTIVE_404S} consecutive 404 errors, likely reached end of data"
                    )
                    break

                current_page += 1
                continue

            if not html:
                logging.error(f"Failed to fetch page {current_page}, stopping")
                break

            # Сбросить счётчик последовательных 404
            consecutive_404s = 0

            vessels_on_page = parse_vessel_list_page(html)

            if not vessels_on_page:
                logging.warning(f"No vessels found on page {current_page}, stopping")
                break

            logging.info(
                f"Found {len(vessels_on_page)} vessels on page {current_page}. Processing with 4 threads..."
            )

            # Обработать суда многопоточно
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(process_vessel, vessel, conn): vessel
                    for vessel in vessels_on_page
                }

                for future in as_completed(futures):
                    vessels_processed += 1
                    total_saved += 1

                    # Проверить лимит судов
                    if max_vessels and vessels_processed >= max_vessels:
                        break

            # Сохранить состояние после обработки страницы
            save_state(conn, mode, current_page, vessels_processed)

            # Перейти к следующей странице
            current_page += 1

            # Периодические перерывы
            if current_page % config.BREAK_AFTER_PAGES == 0:
                break_duration = random.uniform(
                    config.BREAK_DURATION_MIN, config.BREAK_DURATION_MAX
                )
                logging.info(
                    f"Taking a break for {break_duration:.1f}s after {config.BREAK_AFTER_PAGES} pages"
                )
                time.sleep(break_duration)
            else:
                # Задержка между страницами
                delay = random.uniform(
                    config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX
                )
                time.sleep(delay)

    except KeyboardInterrupt:
        logging.info("Scraper interrupted by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    finally:
        # Сохранить финальное состояние
        save_state(conn, mode, current_page, vessels_processed)
        conn.close()
        logging.info(
            f"Scraper finished. Total saved: {total_saved}, total processed: {vessels_processed}"
        )


if __name__ == "__main__":
    main()
