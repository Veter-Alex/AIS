"""Настройка логов скраперов: stderr + файл в logs/scrapers/<имя>.log."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FMT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 7


def _repo_root() -> Path:
    # Локально: AIS_scrapers/common/ -> корень репозитория.
    # В Docker: /app/common/ -> каталог сервиса /app (нет sibling marinetraffic).
    here = Path(__file__).resolve().parent
    scrapers_root = here.parent
    if (scrapers_root / "marinetraffic").is_dir():
        return scrapers_root.parent
    return scrapers_root


def _log_base_dir() -> Path:
    raw = os.environ.get("AIS_LOG_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (_repo_root() / "logs").resolve()


def configure_scraper_logging(component: str) -> None:
    """Консоль и ротируемый лог-файл для процесса скрапера."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    base = _log_base_dir()
    scraper_dir = base / "scrapers"
    scraper_dir.mkdir(parents=True, exist_ok=True)
    log_path = scraper_dir / f"{component}.log"

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_LOG_FMT, _DATE_FMT)

    root.handlers.clear()
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(level)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    fh = RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(formatter)
    root.addHandler(fh)
