import logging
import os
import random
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

URL = os.getenv(
    "DEBUG_VESSEL_URL", "https://www.vesselfinder.com/vessels/details/9648714"
)
USER_AGENT_ENV = os.getenv("DEBUG_USER_AGENT")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]


def choose_user_agent() -> str:
    if USER_AGENT_ENV:
        return USER_AGENT_ENV
    return random.choice(USER_AGENTS)


def fetch_html(url: str) -> str:
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    ua = choose_user_agent()
    opts.add_argument(f"--user-agent={ua}")
    opts.binary_location = os.getenv("CHROME_BIN", "/usr/bin/chromium")
    service = Service(os.getenv("CHROMEDRIVER_BIN", "/usr/bin/chromedriver"))
    driver = None
    try:
        logging.info(f"Using User-Agent: {ua}")
        driver = webdriver.Chrome(service=service, options=opts)
        driver.get(url)
        time.sleep(3)
        html = driver.page_source
        return html
    finally:
        if driver:
            driver.quit()


def summarize(html: str):
    length = len(html)
    print(f"\n===== RAW HTML LENGTH: {length} bytes =====")
    print("===== RAW HTML FIRST 2000 CHARS =====")
    print(html[:2000].replace("\n", "\n") if html else "NO HTML")
    # Optionally write full HTML to file for manual inspection
    out_path = "debug_page.html"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nSaved full HTML to {out_path}")
    except Exception as e:
        print(f"Failed to save HTML: {e}")

    soup = BeautifulSoup(html, "html.parser")
    print("\n===== PAGE TITLE =====")
    print(soup.title.text.strip() if soup.title else "NO TITLE")
    print("\n===== TABLE SUMMARY (up to 12) =====")
    tables = soup.find_all("table")
    for idx, tbl in enumerate(tables[:12]):
        headers = [th.get_text(strip=True) for th in tbl.find_all("th")][:8]
        text_sample = tbl.get_text(" ", strip=True)[:220]
        class_attr = " ".join(tbl.get("class", []))
        print(
            f'[# {idx}] class="{class_attr}" headers={headers} sample="{text_sample}"'
        )
    print("\n===== IMAGE CANDIDATES (up to 12) =====")
    for img in soup.find_all("img")[:12]:
        src = img.get("src") or img.get("data-src")
        alt = img.get("alt")
        cls = " ".join(img.get("class", []))
        if src:
            print(f'IMG class="{cls}" alt="{alt}" src="{src}"')
    print("\n===== IMO / MMSI RAW CONTEXT (first 25 lines) =====")
    body_text = soup.get_text("\n", strip=True)
    lines = [l for l in body_text.split("\n") if "IMO" in l or "MMSI" in l]
    for l in lines[:25]:
        print(l)
    print("\n===== LENGTH / BEAM / DWT / GT / YEAR CONTEXT (heuristic) =====")
    metrics_lines = [
        l
        for l in body_text.split("\n")
        if any(k in l for k in ["Length", "Beam", "DWT", "GT", "Built", "Year"])
    ]
    for l in metrics_lines[:30]:
        print(l)


def main():
    logging.info(f"Fetching HTML for {URL}")
    html = fetch_html(URL)
    summarize(html)


if __name__ == "__main__":
    main()
