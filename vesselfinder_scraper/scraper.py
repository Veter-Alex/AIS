import logging
import os
import random
import re
import time
from datetime import datetime

import config
import psycopg2
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def get_db_conn():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", config.DB_NAME),
        user=os.getenv("POSTGRES_USER", config.DB_USER),
        password=os.getenv("POSTGRES_PASSWORD", config.DB_PASSWORD),
        host=os.getenv("POSTGRES_HOST", config.DB_HOST),
        port=os.getenv("POSTGRES_PORT", config.DB_PORT),
    )


def get_scraper_state(mode):
    """Получить состояние скрапера для заданного режима"""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT last_page, vessels_count FROM scraper_state WHERE mode = %s",
            (mode,),
        )
        result = cur.fetchone()
        if result:
            last_page, vessels_count = result
            logging.info(
                f"Загружено состояние для режима '{mode}': страница {last_page}, судов {vessels_count}"
            )
            return last_page, vessels_count
        logging.info(f"Состояние для режима '{mode}' не найдено, начинаем с начала")
        return 1, 0
    finally:
        cur.close()
        conn.close()


def save_scraper_state(mode, last_page, vessels_count):
    """Сохранить состояние скрапера"""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO scraper_state (mode, last_page, vessels_count, last_run_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (mode) DO UPDATE SET
                last_page = EXCLUDED.last_page,
                vessels_count = EXCLUDED.vessels_count,
                last_run_at = EXCLUDED.last_run_at
            """,
            (mode, last_page, vessels_count),
        )
        conn.commit()
        logging.info(
            f"Состояние сохранено: режим '{mode}', страница {last_page}, судов {vessels_count}"
        )
    finally:
        cur.close()
        conn.close()


def download_image(photo_url, vessel_key):
    import requests

    if not photo_url or not vessel_key:
        return None
    image_dir = os.getenv("IMAGE_DIR", "/app/images")
    os.makedirs(image_dir, exist_ok=True)
    ext = ".jpg"
    if photo_url.lower().endswith(".png"):
        ext = ".png"
    file_name = f"{vessel_key}{ext}"
    dest = os.path.join(image_dir, file_name)
    try:
        r = requests.get(photo_url, timeout=config.PHOTO_DOWNLOAD_TIMEOUT)
        if r.status_code == 200:
            with open(dest, "wb") as f:
                f.write(r.content)
            logging.info(f"Фото сохранено: {dest}")
            return dest
        logging.warning(f"Фото не скачано status={r.status_code}")
        return None
    except Exception as e:
        logging.warning(f"Ошибка скачивания фото: {e}")
        return None


def save_to_db(vessel):
    conn = get_db_conn()
    cur = conn.cursor()
    imo = vessel.get("imo")
    mmsi = vessel.get("mmsi")
    logging.info(f"save_to_db: name={vessel.get('name')} imo={imo} mmsi={mmsi}")
    if not imo and not mmsi:
        logging.warning("Пропуск записи: нет IMO и MMSI")
        cur.close()
        conn.close()
        return
    vessel_key = imo if imo else mmsi
    sql = """
    INSERT INTO vessels (
        name, imo, mmsi, call_sign, general_type, detailed_type, flag, year_built, length, width, dwt, gt, home_port, photo_url, photo_path, description, info_source, updated_at, vessel_key
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (vessel_key) DO UPDATE SET
        name=EXCLUDED.name,
        imo=EXCLUDED.imo,
        mmsi=EXCLUDED.mmsi,
        call_sign=EXCLUDED.call_sign,
        general_type=EXCLUDED.general_type,
        detailed_type=EXCLUDED.detailed_type,
        flag=EXCLUDED.flag,
        year_built=EXCLUDED.year_built,
        length=EXCLUDED.length,
        width=EXCLUDED.width,
        dwt=EXCLUDED.dwt,
        gt=EXCLUDED.gt,
        home_port=EXCLUDED.home_port,
        photo_url=EXCLUDED.photo_url,
        photo_path=EXCLUDED.photo_path,
        description=EXCLUDED.description,
        info_source=EXCLUDED.info_source,
        updated_at=EXCLUDED.updated_at;
    """
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
            vessel.get("info_source"),
            vessel.get("updated_at"),
            vessel_key,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()
    logging.info(f"UPSERT выполнен: key={vessel_key}")


def get_html_with_selenium(url, user_agent, retries=0):
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument(f"--user-agent={user_agent}")
    opts.add_argument(f"--window-size={config.WINDOW_SIZE}")
    opts.binary_location = os.getenv("CHROME_BIN", config.CHROME_BINARY)
    service = Service(os.getenv("CHROMEDRIVER_BIN", config.CHROMEDRIVER_BINARY))
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=opts)
        driver.get(url)
        # Явные ожидания ключевых элементов для динамически подгружаемого контента
        wait_timeout = int(os.getenv("WAIT_TIMEOUT", str(config.WAIT_TIMEOUT)))
        wait = WebDriverWait(driver, wait_timeout, poll_frequency=0.5)
        try:
            wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//table[contains(@class,'tpt1')][.//text()[contains(.,'Length Overall')]]",
                    )
                )
            )
            logging.info("Ожидание таблицы Length Overall: OK")
        except TimeoutException:
            logging.warning("Таблица Length Overall не появилась за таймаут")
        try:
            wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//table[contains(@class,'tpt1')][.//text()[contains(.,'Gross Tonnage')]]",
                    )
                )
            )
            logging.info("Ожидание таблицы Gross Tonnage: OK")
        except TimeoutException:
            logging.warning("Таблица Gross Tonnage не появилась за таймаут")
        # Фото (scroll + наличие)
        try:
            photo_el = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "img.main-photo"))
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", photo_el
            )
            logging.info("Ожидание фото: OK")
        except TimeoutException:
            logging.warning("Фото main-photo не появилось за таймаут")
        # Небольшая рандомная задержка для стабилизации DOM
        time.sleep(
            random.uniform(config.DOM_STABILIZATION_MIN, config.DOM_STABILIZATION_MAX)
        )
        html = driver.page_source
        driver.quit()
        return html
    except WebDriverException as e:
        if driver:
            driver.quit()
        if retries < config.MAX_RETRIES:
            wait = config.RETRY_BASE_DELAY**retries
            logging.warning(f"WebDriver ошибка, повтор через {wait}s")
            time.sleep(wait)
            return get_html_with_selenium(url, user_agent, retries + 1)
        logging.error(f"WebDriver окончательная ошибка: {e}")
        return None


def get_vessel_links(page=1, vessel_type=None):
    if vessel_type:
        if page == 1:
            url = f"https://www.vesselfinder.com/vessels?type={vessel_type}"
        else:
            url = f"https://www.vesselfinder.com/vessels?page={page}&type={vessel_type}"
    else:
        url = f"https://www.vesselfinder.com/vessels?page={page}"
    ua = random.choice(config.USER_AGENTS)
    html = get_html_with_selenium(url, ua)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select("table a[href^='/vessels/details/']"):
        href = a.get("href")
        if href:
            links.append("https://www.vesselfinder.com" + href)
    return links


def parse_vessel(url):
    ua = random.choice(config.USER_AGENTS)
    retries = 0
    while retries < config.MAX_RETRIES:
        html = get_html_with_selenium(url, ua)
        if not html:
            retries += 1
            continue
        soup = BeautifulSoup(html, "html.parser")
        vessel = {}
        vessel["info_source"] = "vesselfinder.com"
        vessel["updated_at"] = datetime.utcnow()
        h1 = soup.find("h1")
        vessel["name"] = " ".join(h1.text.split()) if h1 and h1.text else None

        tables = soup.find_all(
            "table", class_=lambda c: c and ("tpt1" in c or "aparams" in c)
        )
        combined = " ".join(t.get_text(" ", strip=True) for t in tables)

        def rx(pattern, flags=0, group=1):
            m = re.search(pattern, combined, flags)
            return m.group(group) if m else None

        vessel["imo"] = rx(r"IMO\s*(\d{7})") or rx(r"IMO number\s*(\d{7})")
        vessel["mmsi"] = rx(r"MMSI\s*(\d{9})")
        vessel["call_sign"] = rx(r"Callsign\s*([A-Z0-9]+)")
        vessel["flag"] = rx(r"Flag\s*([A-Za-z ]+?)\s+Year of Build") or rx(
            r"AIS Flag\s*([A-Za-z]+)"
        )
        vessel["year_built"] = rx(r"Year of Build\s*(\d{4})") or rx(r"Built\s*(\d{4})")
        vessel["general_type"] = rx(r"Ship Type\s*([A-Za-z /-]+?)\s+Flag") or rx(
            r"is a\s+([A-Za-z /-]+?)\s+built", flags=re.IGNORECASE
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
                vessel["mmsi"] = m.group(1)

        def to_int(val):
            if val is None:
                return None
            mnum = re.search(r"\d+", str(val).replace(",", ""))
            return int(mnum.group()) if mnum else None

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
        # Не используем fallback на одиночную цифру после Deadweight, чтобы избежать ложных '3'

        vessel["year_built"] = to_int(vessel.get("year_built"))
        vessel["length"] = to_int(vessel.get("length"))
        vessel["width"] = to_int(vessel.get("width"))
        vessel["dwt"] = to_int(vessel.get("dwt"))
        vessel["gt"] = to_int(vessel.get("gt"))

        img = soup.find("img", class_="main-photo")
        vessel["photo_url"] = img["src"] if img and img.get("src") else None
        vessel_key = vessel.get("imo") or vessel.get("mmsi")
        if vessel["photo_url"] and vessel_key:
            vessel["photo_path"] = download_image(vessel["photo_url"], vessel_key)
        logging.info(
            f"Парсинг судна завершён: name={vessel.get('name')} imo={vessel.get('imo')} mmsi={vessel.get('mmsi')}"
        )
        return vessel
    logging.error(f"Не удалось распарсить после {config.MAX_RETRIES} попыток: {url}")
    return None


def main():
    mode = os.getenv("SCRAPER_MODE", config.MODE)
    logging.info(f"main() started, режим: {mode}")

    # Загружаем сохраненное состояние
    start_page, saved_count = get_scraper_state(mode)

    # Определяем лимиты в зависимости от режима
    if mode == "test":
        max_vessels = config.MAX_VESSELS_TEST
        max_pages = 3  # В тестовом режиме ограничиваем страницы
    else:  # "full"
        max_vessels = config.MAX_VESSELS_FULL
        max_pages = config.MAX_PAGES

    logging.info(f"Лимит судов: {max_vessels if max_vessels else 'без ограничений'}")
    logging.info(f"Лимит страниц: {max_pages if max_pages else 'без ограничений'}")

    count = saved_count
    page = start_page
    vessel_type = (
        int(os.getenv("VESSEL_TYPE", config.VESSEL_TYPE))
        if os.getenv("VESSEL_TYPE") or config.VESSEL_TYPE
        else None
    )
    logging.info(f"Начинаем с страницы {page}, уже обработано судов: {count}")
    if vessel_type:
        logging.info(f"Фильтр по типу судов: {vessel_type}")

    while True:
        # Проверка лимита страниц
        if max_pages and page > max_pages:
            logging.info(f"Достигнут лимит страниц: {max_pages}")
            save_scraper_state(mode, page, count)
            break

        logging.info(f"Парсинг страницы {page}")
        links = get_vessel_links(page, vessel_type)

        if not links:
            logging.info("Нет больше судов для парсинга")
            save_scraper_state(mode, page, count)
            break

        for link in links:
            # Проверка лимита судов
            if max_vessels and count >= max_vessels:
                logging.info(f"Достигнут лимит судов: {max_vessels}")
                save_scraper_state(mode, page, count)
                logging.info("main() finished")
                return

            logging.info(f"Парсинг судна: {link}")
            vessel = parse_vessel(link)
            if vessel:
                save_to_db(vessel)
                count += 1

            delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
            logging.info(f"Задержка {delay:.1f} сек")
            time.sleep(delay)

        # Сохраняем состояние после каждой страницы
        save_scraper_state(mode, page + 1, count)
        page += 1

    save_scraper_state(mode, page, count)
    logging.info(f"main() finished, обработано судов: {count}")


if __name__ == "__main__":
    main()
