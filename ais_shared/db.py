"""
Утилиты подключения к PostgreSQL (общие для API-сервисов).
"""

import os
from contextlib import contextmanager

from psycopg2.pool import ThreadedConnectionPool

_DB_POOL = None


class _PooledConnection:
    """Обертка, чтобы conn.close() возвращал соединение в пул."""

    def __init__(self, pool: ThreadedConnectionPool, conn):
        self._pool = pool
        self._conn = conn
        self._released = False

    def __getattr__(self, item):
        return getattr(self._conn, item)

    def close(self):
        if not self._released:
            self._pool.putconn(self._conn)
            self._released = True


def _get_pool() -> ThreadedConnectionPool:
    global _DB_POOL
    if _DB_POOL is None:
        min_conn = int(os.getenv("DB_POOL_MIN_CONN", "1"))
        max_conn = int(os.getenv("DB_POOL_MAX_CONN", "10"))
        _DB_POOL = ThreadedConnectionPool(
            min_conn,
            max_conn,
            dbname=os.getenv("POSTGRES_DB", "vessels_db"),
            user=os.getenv("POSTGRES_USER", "user"),
            password=os.getenv("POSTGRES_PASSWORD", "password"),
            host=os.getenv("POSTGRES_HOST", "db"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            connect_timeout=int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5")),
            options=f"-c statement_timeout="
            f"{os.getenv('POSTGRES_STATEMENT_TIMEOUT_MS', '60000')}",
        )
    return _DB_POOL


def get_db_conn():
    """Создать подключение к PostgreSQL.

    Возвращает:
    - psycopg2 connection, который вызывающая сторона обязана закрыть.
    """
    pool = _get_pool()
    return _PooledConnection(pool, pool.getconn())


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

    Хелпер для batch-сценариев, где прогресс и данные пишутся разными
    транзакциями.
    """
    conn = get_db_conn()
    meta_conn = get_db_conn()
    try:
        yield conn, meta_conn
    finally:
        conn.close()
        meta_conn.close()
