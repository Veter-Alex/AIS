"""
Скрапер Maritime Database.

Описание:
- Загружает списки судов и страницы деталей, извлекает структурированные поля
    и сохраняет их в базу данных.
- Реализованы задержки, повторные попытки и мягкая параллельность для снижения
    риска блокировки со стороны сайта.
- Включён многоуровневый предохранитель для очистки поля `general_type`,
    исключающий случаи склейки имени судна и типа (например,
    "MSC BRIDGERo-Ro Cargo Ship").

Стиль:
- Докстринги и комментарии на русском языке в соответствии с PEP8.
- Имена функций и переменных следуют стандартам PEP8.
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


def sanitize_general_type(name, vessel_type):
    """Очистить `general_type`, убрав префикс имени судна, если он склеен.

    Параметры:
    - name: строка с именем судна (или None).
    - vessel_type: строка с типом судна (или None).

    Возвращает:
    - Строку с типом судна без ведущего имени, либо исходное значение,
      если очистка не требуется.

    Примечание:
    - Нормализует пробелы перед сравнением.
    """
    if not name or not vessel_type:
        return vessel_type
    name_norm = re.sub(r"\s+", " ", str(name)).strip()
    type_norm = re.sub(r"\s+", " ", str(vessel_type)).strip()
    if type_norm.startswith(name_norm):
        cleaned = type_norm[len(name_norm) :].strip()
        return cleaned if cleaned else vessel_type
    return vessel_type


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
            ("maritime_database", mode),
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
            ("maritime_database", mode, last_page, vessels_count),
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

    # Финальный предохранитель: очистить general_type перед записью
    vessel["general_type"] = sanitize_general_type(
        vessel.get("name"), vessel.get("general_type")
    )

    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
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
                    WHEN vessels.info_source = 'vesselfinder.com' THEN vessels.info_source
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
                "maritime-database.com",
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


def fetch_page(url, retries=0):
    """Загрузить страницу по URL с логикой повторных попыток.

    Использует общий `requests.Session` для переиспользования соединений.

    Параметры:
    - url: адрес страницы.
    - retries: текущий номер попытки (для рекурсивного экспоненциального бэкоффа).

    Возвращает:
    - Текст HTML или None при неудаче после `config.MAX_RETRIES`.
    """
    headers = {"User-Agent": random.choice(config.USER_AGENTS)}

    try:
        # Использовать глобальный объект сессии
        response = session.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except Exception as e:
        if retries < config.MAX_RETRIES:
            delay = config.RETRY_BASE_DELAY * (2**retries)
            logging.warning(f"Error fetching {url}: {e}. Retrying in {delay}s...")
            time.sleep(delay)
            return fetch_page(url, retries + 1)
        logging.error(f"Failed to fetch {url} after {config.MAX_RETRIES} retries")
        return None


def parse_vessel_list_page(html):
    """Распарсить страницу списка судов и вернуть краткие данные.

    Возвращает список словарей с полями:
    - url, name, general_type, year_built, gt, dwt, dimensions.
    """
    soup = BeautifulSoup(html, "html.parser")
    vessels = []

    # Найти все строки судов в таблице
    rows = soup.find_all("tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 6:  # Строка с данными судна
            link_cell = cells[0].find("a")
            if link_cell and link_cell.get("href"):
                vessel_url = "https://www.maritime-database.com" + link_cell["href"]
                vessel_name = link_cell.text.strip()

                # Базовая информация из таблицы списка
                vessel_type = cells[1].text.strip() if len(cells) > 1 else None
                # Очистка: некоторые строки содержат склейку имени и типа
                vessel_type = sanitize_general_type(vessel_name, vessel_type)
                year_built = cells[2].text.strip() if len(cells) > 2 else None
                gt = cells[3].text.strip() if len(cells) > 3 else None
                dwt = cells[4].text.strip() if len(cells) > 4 else None
                dimensions = cells[5].text.strip() if len(cells) > 5 else None

                vessels.append(
                    {
                        "url": vessel_url,
                        "name": vessel_name,
                        "general_type": vessel_type,
                        "year_built": (
                            int(year_built)
                            if year_built and year_built.isdigit()
                            else None
                        ),
                        "gt": int(gt) if gt and gt.isdigit() else None,
                        "dwt": int(dwt) if dwt and dwt.isdigit() else None,
                        "dimensions": dimensions,
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

    # Извлечь VESSEL_ID из URL или данных страницы (нужен для URL фото)
    vessel_id = None
    url = vessel_data.get("url")
    logging.info(f"Processing vessel URL: {url}")
    if url:
        vessel_id_match = re.search(r"vesselid:(\d+)", url)
        if vessel_id_match:
            vessel_id = vessel_id_match.group(1)
            logging.debug(f"Extracted vessel_id: {vessel_id} from {url}")
        else:
            logging.warning(f"Could not extract vessel_id from URL: {url}")

    # Извлечь имя судна из поля "Vessel Name:" или из описания
    vessel_name = extract_field(
        r"Vessel\s+Name[:\s]*([A-Z0-9\s\-\.]+?)(?=Type:|Country:|\n)"
    )
    if vessel_name:
        vessel_data["name"] = vessel_name

    # Если имя не найдено, попытаться извлечь из описания (формат: "NAME built in YEAR...")
    if not vessel_data.get("name"):
        # Найти имя судна перед паттерном "built in YYYY"
        desc_match = re.search(
            r"([A-Z][A-Z0-9\s\-\.]+?)\s+built\s+in\s+\d{4}", text, re.IGNORECASE
        )
        if desc_match:
            vessel_data["name"] = desc_match.group(1).strip()

    # Извлечь структурированные поля из страницы деталей
    # Эти поля имеют приоритет над данными со страницы списка
    mmsi = extract_field(r"MMSI[:\s]+(\d{9})")
    imo = extract_field(r"IMO[:\s]+(\d{7})")
    call_sign = extract_field(
        r"CALLSIGN[:\s]*([A-Z0-9]+?)(?=\s*Lengthbeam|\s*Length|\n)"
    )

    # Извлечь тип судна из поля Type: (чище, чем на странице списка)
    vessel_type = extract_field(r"Type[:\s]*([A-Za-z\s/]+?)(?=Country|\n)")

    # Очистка типа, если он начинается с имени (предохранитель)
    sanitized_type = sanitize_general_type(vessel_data.get("name"), vessel_type)
    if sanitized_type != vessel_type:
        logging.warning(
            f"Sanitized general_type: '{vessel_type}' -> '{sanitized_type}'"
        )
        vessel_type = sanitized_type

    # Извлечь страну/флаг
    flag = extract_field(r"Country[:\s]*([A-Za-z\s\(\)]+?)(?=IMO|\n)")

    # Извлечь размеры из поля Lengthbeam
    lengthbeam = extract_field(r"Lengthbeam[:\s]*(\d+)\s*/\s*(\d+)")
    if lengthbeam:
        length_match = re.search(
            r"Lengthbeam[:\s]*(\d+)\s*/\s*(\d+)", text, re.IGNORECASE
        )
        if length_match:
            vessel_data["length"] = int(length_match.group(1))
            vessel_data["width"] = int(length_match.group(2))

    # Извлечь валовую вместимость
    gross = extract_field(r"Gross[:\s]*(\d+)")
    if gross:
        vessel_data["gt"] = int(gross)

    # Извлечь DWT летом
    summer_dwt = extract_field(r"Summer\s+DWT[:\s]*(\d+)")
    if summer_dwt:
        vessel_data["dwt"] = int(summer_dwt)

    # Извлечь год постройки
    year_built = extract_field(r"Year\s+Built[:\s]*(\d{4})")
    if year_built:
        vessel_data["year_built"] = int(year_built)

    # Извлечь описание из секции Description
    description = extract_field(
        r"Description\s*([\s\S]+?)(?=Similar Vessels|Latest reported|$)"
    )
    if description:
        # Очистить описание (удалить лишние пробелы)
        description = re.sub(r"\s+", " ", description).strip()
        vessel_data["description"] = description[:1000]  # Ограничить длину

    # Обновить vessel_data информацией со страницы деталей (нужно для конструирования URL фото)
    if mmsi:
        vessel_data["mmsi"] = mmsi
    if imo:
        vessel_data["imo"] = imo
    if call_sign:
        vessel_data["call_sign"] = call_sign
    if vessel_type:
        vessel_data["general_type"] = vessel_type
    if flag:
        vessel_data["flag"] = flag

    # Извлечь URL фото
    # Maritime Database использует JavaScript для динамической загрузки изображений, поэтому их нет в HTML
    # Нужно сконструировать URL. Каталог зависит от vessel_id: (id // 1000) + 1
    photo_found = False
    current_mmsi = mmsi or vessel_data.get("mmsi")

    if current_mmsi:
        mmsi_str = str(current_mmsi)
        directories_to_check = []

        # Вычислить каталог из vessel_id, если доступен
        if vessel_id:
            try:
                # Формула: folder = (vessel_id // 1000) + 1
                # Пример: 22245 -> 23; 49 -> 1
                calc_dir = (int(vessel_id) // 1000) + 1
                directories_to_check.append(calc_dir)
            except ValueError:
                logging.warning(f"Invalid vessel_id for photo calculation: {vessel_id}")

        # Запасной диапазон, если расчёт не удался (опционально, но безопасно)
        if not directories_to_check:
            directories_to_check = range(1, 15)

        for directory in directories_to_check:
            photo_url = f"https://www.maritime-database.com/upload/vessels_images/{directory}/{mmsi_str}.jpg"
            try:
                # Проверить существование фото с помощью HEAD-запроса через сессию
                headers = {"User-Agent": random.choice(config.USER_AGENTS)}
                response = session.head(photo_url, headers=headers, timeout=5)
                if response.status_code == 200:
                    vessel_data["photo_url"] = photo_url
                    photo_found = True
                    logging.info(f"Found photo URL: {photo_url}")
                    break
            except Exception as e:
                logging.debug(f"Error checking photo URL {photo_url}: {e}")
                continue

    if not photo_found:
        logging.warning(
            f"No photo found for vessel {vessel_data.get('name')} (mmsi={current_mmsi})"
        )

    # Скачать фото, если photo_url существует
    vessel_key = vessel_data.get("imo") or vessel_data.get("mmsi")
    if vessel_data.get("photo_url") and vessel_key:
        vessel_data["photo_path"] = download_image(vessel_data["photo_url"], vessel_key)

    # Сгенерировать vessel_key из MMSI
    if vessel_data.get("mmsi"):
        vessel_data["vessel_key"] = vessel_data["mmsi"]

    return vessel_data


def process_vessel(vessel_data):
    """Обработать одно судно: загрузить детали, распарсить и сохранить.

    Включает небольшую случайную задержку для рассинхронизации потоков.
    Возвращает True при успешной записи, иначе False.
    """
    try:
        # Небольшая случайная задержка для предотвращения одновременных запросов от всех потоков
        time.sleep(random.uniform(0.5, 1.5))

        detail_html = fetch_page(vessel_data["url"])
        if detail_html:
            vessel_data = parse_vessel_detail_page(detail_html, vessel_data)
            if save_vessel(vessel_data):
                return True
    except Exception as e:
        logging.error(f"Error processing vessel {vessel_data.get('url')}: {e}")
    return False


def main():
    """Точка входа скрапера Maritime Database.

    Управление режимом через ENV `SCRAPER_MODE`: "test" или "full".
    Использует сохранение состояния для продолжения работы с нужной страницы.
    """
    mode = os.getenv("SCRAPER_MODE", "test")
    logging.info(f"Maritime Database Scraper started, mode: {mode}")

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

    # Количество параллельных потоков (консервативно, чтобы избежать блокировки)
    MAX_WORKERS = 4

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
            if current_page == 1:
                url = config.BASE_URL
            else:
                start = (current_page - 1) * config.VESSELS_PER_PAGE
                url = f"{config.BASE_URL}?start={start}&count={config.VESSELS_PER_PAGE}"

            logging.info(f"Fetching page {current_page}: {url}")

            # Загрузить и распарсить страницу списка
            html = fetch_page(url)
            if not html:
                logging.error(f"Failed to fetch page {current_page}")
                break

            vessels = parse_vessel_list_page(html)
            if not vessels:
                logging.info("No more vessels found")
                break

            logging.info(
                f"Found {len(vessels)} vessels on page {current_page}. Processing with {MAX_WORKERS} threads..."
            )

            # Обработать суда параллельно
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for vessel_data in vessels:
                    if max_vessels and vessels_processed >= max_vessels:
                        break
                    futures.append(executor.submit(process_vessel, vessel_data))

                for future in as_completed(futures):
                    if future.result():
                        total_saved += 1
                        vessels_processed += 1

            # Сохранить состояние после каждой страницы
            save_scraper_state(mode, current_page, vessels_processed)
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


if __name__ == "__main__":
    main()
