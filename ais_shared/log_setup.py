"""Файловое логирование сервиса (дополняет вывод uvicorn в stderr)."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FMT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 7


def _repo_root() -> Path:
    # ais_shared/ лежит в корне репозитория; в Docker — под /app/ais_shared.
    return Path(__file__).resolve().parent.parent


def _log_base_dir() -> Path:
    raw = os.environ.get("AIS_LOG_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (_repo_root() / "logs").resolve()


def configure_service_logging(service_dir: str) -> None:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    base = _log_base_dir()
    out_dir = base / service_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = (out_dir / "app.log").resolve()

    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(_LOG_FMT, _DATE_FMT)

    path_norm = os.path.normcase(str(log_path))
    for h in root.handlers:
        if (
            isinstance(h, RotatingFileHandler)
            and os.path.normcase(getattr(h, "baseFilename", "")) == path_norm
        ):
            return

    fh = RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(formatter)
    root.addHandler(fh)
