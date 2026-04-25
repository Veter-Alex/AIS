"""
Утилиты подключения к PostgreSQL для ai_agent.
"""

import os
from contextlib import contextmanager

import psycopg2


def get_db_conn():
    """Создать подключение к PostgreSQL."""
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "vessels_db"),
        user=os.getenv("POSTGRES_USER", "user"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
        host=os.getenv("POSTGRES_HOST", "db"),
        port=os.getenv("POSTGRES_PORT", "5432"),
    )


@contextmanager
def get_db_cursor(cursor_factory=None, commit: bool = False):
    """Создать курсор БД и гарантированно закрыть ресурсы.

    Параметры:
    - cursor_factory: фабрика курсора (например RealDictCursor).
    - commit: выполнить commit после успешного блока (для write-операций).
    """
    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=cursor_factory)
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@contextmanager
def get_db_connections():
    """Выдать пару соединений: основное и meta.

    Используется в ingestion-сценариях, где:
    - основное соединение работает с транзакцией данных;
    - meta-соединение пишет прогресс задач отдельно.
    """
    conn = get_db_conn()
    meta_conn = get_db_conn()
    try:
        yield conn, meta_conn
    finally:
        conn.close()
        meta_conn.close()
