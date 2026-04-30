"""
Диагностический утилитарный скрипт для отладки HTML страницы судна на VesselFinder.

Назначение:
- быстро получить сырой HTML через HTTP (как основной скрапер);
- вывести ключевые фрагменты (таблицы, изображения, метрики IMO/MMSI);
- сохранить страницу в файл для ручного анализа селекторов.
"""

import logging
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

_SCRAPERS_ROOT = Path(__file__).resolve().parent.parent
_SCRAPER_DIR = Path(__file__).resolve().parent
for p in (_SCRAPERS_ROOT, _SCRAPER_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
from common.http import fetch_page_with_retry  # noqa: E402
from common.logging_setup import configure_scraper_logging  # noqa: E402
import config  # noqa: E402

configure_scraper_logging("vesselfinder_debug")

URL = os.getenv(
    "DEBUG_VESSEL_URL", "https://www.vesselfinder.com/vessels/details/9648714"
)
USER_AGENT_ENV = os.getenv("DEBUG_USER_AGENT")


def fetch_html(url: str) -> str:
    session = requests.Session()
    user_agents = (
        [USER_AGENT_ENV] if USER_AGENT_ENV else config.USER_AGENTS
    )
    html = fetch_page_with_retry(
        session=session,
        url=url,
        user_agents=user_agents,
        timeout=30,
        max_retries=config.MAX_RETRIES,
        retry_delay_range=(config.RETRY_DELAY_MIN, config.RETRY_DELAY_MAX),
    )
    if not html or html == "404_NOT_FOUND":
        raise RuntimeError(f"Не удалось загрузить {url}")
    return html


def summarize(html: str):
    # Печатаем ключевые диагностические блоки, чтобы быстро понять,
    # какие селекторы/данные доступны в текущей версии страницы.
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
    lines = [
        line
        for line in body_text.split("\n")
        if "IMO" in line or "MMSI" in line
    ]
    for line in lines[:25]:
        print(line)
    print("\n===== LENGTH / BEAM / DWT / GT / YEAR CONTEXT (heuristic) =====")
    metrics_lines = [
        line
        for line in body_text.split("\n")
        if any(
            k in line for k in ["Length", "Beam", "DWT", "GT", "Built", "Year"]
        )
    ]
    for line in metrics_lines[:30]:
        print(line)


def main():
    # Точка входа: скачиваем HTML и печатаем подробную сводку для отладки.
    logging.info(f"Fetching HTML for {URL}")
    html = fetch_html(URL)
    summarize(html)


if __name__ == "__main__":
    main()
