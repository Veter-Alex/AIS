"""Общие утилиты работы с PostgreSQL для скраперов."""

import os
from datetime import datetime
from typing import Tuple

import psycopg2


def get_db_conn(
    default_db: str = "vessels_db",
    default_user: str = "user",
    default_password: str = "password",
    default_host: str = "db",
    default_port: str = "5432",
):
    """Создать подключение к PostgreSQL с ENV fallback."""
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", default_db),
        user=os.getenv("POSTGRES_USER", default_user),
        password=os.getenv("POSTGRES_PASSWORD", default_password),
        host=os.getenv("POSTGRES_HOST", default_host),
        port=os.getenv("POSTGRES_PORT", default_port),
    )


def load_scraper_state(conn, scraper_name: str, mode: str) -> Tuple[int, int]:
    """Загрузить состояние скрапера (last_page, vessels_count)."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT last_page, vessels_count
            FROM scraper_state
            WHERE scraper_name = %s AND mode = %s
            """,
            (scraper_name, mode),
        )
        row = cur.fetchone()
        if not row:
            return 1, 0
        return int(row[0]), int(row[1])
    finally:
        cur.close()


def save_scraper_state(
    conn,
    scraper_name: str,
    mode: str,
    last_page: int,
    vessels_count: int,
):
    """Сохранить состояние скрапера (upsert)."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO scraper_state (scraper_name, mode, last_page, vessels_count, last_run_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (scraper_name, mode) DO UPDATE SET
                last_page = EXCLUDED.last_page,
                vessels_count = EXCLUDED.vessels_count,
                last_run_at = EXCLUDED.last_run_at
            """,
            (scraper_name, mode, last_page, vessels_count, datetime.now()),
        )
        conn.commit()
    finally:
        cur.close()

