import logging
import os
import random
import re
import time
from datetime import datetime

import psycopg2
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

MAX_RETRIES = 5


def get_db_conn():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "vessels_db"),
        user=os.getenv("POSTGRES_USER", "user"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )


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
        r = requests.get(photo_url, timeout=15)
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
        name, imo, mmsi, call_sign, general_type, detailed_type, flag, year_built, length, width, dwt, gt, home_port, photo_url, photo_path, info_source, updated_at, vessel_key
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
        info_source=EXCLUDED.info_source,
        updated_at=EXCLUDED.updated_at;
    """
    cur.execute(
        sql,
        (
            vessel.get("name"),
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
    opts.add_argument("--window-size=1920,1080")
    opts.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    service = Service(os.getenv("CHROMEDRIVER_BIN", "/usr/bin/chromedriver"))
    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=opts)
        driver.get(url)
        # Явные ожидания ключевых элементов для динамически подгружаемого контента
        wait_timeout = int(os.getenv("WAIT_TIMEOUT", "12"))
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
        time.sleep(random.uniform(0.8, 1.6))
        html = driver.page_source
        driver.quit()
        return html
    except WebDriverException as e:
        if driver:
            driver.quit()
        if retries < MAX_RETRIES:
            wait = 2**retries
            logging.warning(f"WebDriver ошибка, повтор через {wait}s")
            time.sleep(wait)
            return get_html_with_selenium(url, user_agent, retries + 1)
        logging.error(f"WebDriver окончательная ошибка: {e}")
        return None


def get_vessel_links(page=1):
    url = f"https://www.vesselfinder.com/vessels?page={page}"
    ua = random.choice(USER_AGENTS)
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
    ua = random.choice(USER_AGENTS)
    retries = 0
    while retries < MAX_RETRIES:
        html = get_html_with_selenium(url, ua)
        if not html:
            retries += 1
            continue
        soup = BeautifulSoup(html, "html.parser")
        vessel = {}
        vessel["info_source"] = "vesselfinder.com"
        vessel["updated_at"] = datetime.utcnow()
        h1 = soup.find("h1")
        vessel["name"] = h1.text.strip() if h1 else None

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
    logging.error(f"Не удалось распарсить после {MAX_RETRIES} попыток: {url}")
    return None


def main():
    logging.info("main() started")
    max_vessels = 5
    count = 0
    for page in range(1, 3):
        logging.info(f"Парсинг страницы {page}")
        links = get_vessel_links(page)
        for link in links:
            if count >= max_vessels:
                logging.info(f"Достигнут лимит {max_vessels}")
                logging.info("main() finished")
                return
            logging.info(f"Парсинг судна: {link}")
            vessel = parse_vessel(link)
            if vessel:
                save_to_db(vessel)
                count += 1
            delay = random.uniform(3, 8)
            logging.info(f"Задержка {delay:.1f} сек")
            time.sleep(delay)
    logging.info("main() finished")


if __name__ == "__main__":
    main()
