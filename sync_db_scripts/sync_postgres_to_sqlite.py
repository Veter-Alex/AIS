"""
Синхронизация данных из PostgreSQL в SQLite.

Назначение:
- перенести данные по судам из основной PostgreSQL БД в локальную SQLite БД;
- не дублировать уже существующие MMSI;
- поддерживать безопасный пробный запуск через dry-run.

Ключевые принципы:
- источником истины считается PostgreSQL;
- идентификатор дедупликации — MMSI;
- ошибки подключения и вставки логируются максимально явно.
"""

import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

def _build_postgres_config():
    """Собрать конфиг PostgreSQL из переменных окружения."""
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "database": os.getenv("POSTGRES_DB", "vessels_db"),
        "user": os.getenv("POSTGRES_USER", "user"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


POSTGRES_CONFIG = _build_postgres_config()

# Путь к SQLite БД:
# - через SQLITE_DB_PATH, если задан;
# - иначе относительный путь от скрипта.
DEFAULT_SQLITE_DB_PATH = (
    Path(__file__).parent.parent / "База Данных PKS" / "ShipsDataBase" / "ships_database.sqb"
)
SQLITE_DB_PATH = Path(os.getenv("SQLITE_DB_PATH", str(DEFAULT_SQLITE_DB_PATH)))


def connect_postgres():
    """Подключиться к PostgreSQL.

    Возвращает:
    - активное psycopg2-соединение.
    """
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        raise


def connect_sqlite():
    """Подключиться к SQLite.

    Возвращает:
    - активное sqlite3-соединение с row_factory=sqlite3.Row.
    """
    try:
        conn = sqlite3.connect(str(SQLITE_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"❌ Ошибка подключения к SQLite: {e}")
        raise


def get_existing_mmsi_in_sqlite(sqlite_conn):
    """Получить множество всех MMSI, которые уже есть в SQLite.

    Это множество используется как быстрый фильтр для отбора новых записей.
    """
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT DISTINCT mmsi FROM ships WHERE mmsi IS NOT NULL")
    existing_mmsi = {row[0] for row in cursor.fetchall()}
    cursor.close()
    return existing_mmsi


def iter_vessels_from_postgres(postgres_conn, batch_size=1000):
    """Итерировать суда из PostgreSQL батчами для снижения потребления памяти."""
    with postgres_conn.cursor(name="vessels_sync_cursor", cursor_factory=RealDictCursor) as cursor:
        cursor.itersize = batch_size
        cursor.execute(
            """
            SELECT 
                mmsi, 
                imo, 
                name, 
                flag, 
                call_sign,
                general_type,
                year_built,
                length,
                width,
                dwt,
                gt,
                detailed_type
            FROM vessels
            WHERE mmsi IS NOT NULL
            ORDER BY mmsi
            """
        )
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield row


def insert_vessel_to_sqlite(sqlite_conn, vessel):
    """Вставить/обновить судно в SQLite.

    Преобразования полей:
    - detailed_type имеет приоритет над general_type;
    - call_sign маппится в ship_class;
    - дополнительные размерные метрики сериализуются в reserved_text.
    """
    cursor = sqlite_conn.cursor()

    try:
        cursor.execute(
            """
            INSERT OR REPLACE INTO ships (
                mmsi, imo, name, country, type, 
                ship_class, reserved_int, reserved_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                vessel.get("mmsi"),
                vessel.get("imo"),
                vessel.get("name"),
                vessel.get("flag"),
                vessel.get("detailed_type")
                or vessel.get("general_type"),  # Приоритет на detailed_type
                vessel.get("call_sign"),  # ship_class → call_sign
                vessel.get("year_built"),  # reserved_int → год
                f"Length: {vessel.get('length')}, Width: {vessel.get('width')}, DWT: {vessel.get('dwt')}, GT: {vessel.get('gt')}",  # reserved_text
            ),
        )
        return True
    except sqlite3.Error as e:
        print(f"⚠️  Ошибка при вставке MMSI {vessel.get('mmsi')}: {e}")
        return False


def sync_databases(dry_run=False, batch_size=1000):
    """Основная функция синхронизации PostgreSQL -> SQLite.

    Параметры:
    - dry_run: если True, только показывает планируемые изменения без записи.
    """
    print(f"🔄 Синхронизация PostgreSQL → SQLite")
    print(f"📍 SQLite: {SQLITE_DB_PATH}")
    print(
        f"📍 PostgreSQL: {POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}"
    )
    print()

    try:
        # Подключиться к обеим БД
        print("🔗 Подключение к БД...")
        postgres_conn = connect_postgres()
        sqlite_conn = connect_sqlite()

        # Блокируем SQLite на запись, чтобы избежать параллельных гонок sync-процессов.
        sqlite_conn.execute("BEGIN IMMEDIATE")

        # Получить существующие MMSI в SQLite
        print("📊 Анализ существующих MMSI в SQLite...")
        existing_mmsi = get_existing_mmsi_in_sqlite(sqlite_conn)
        print(f"   Найдено {len(existing_mmsi)} записей в SQLite")

        print("📊 Потоковая загрузка данных из PostgreSQL...")

        if dry_run:
            print("🧪 DRY RUN - изменения не применяются")
            samples = []
            new_count = 0
            total_count = 0
            for vessel in iter_vessels_from_postgres(postgres_conn, batch_size=batch_size):
                total_count += 1
                if vessel["mmsi"] in existing_mmsi:
                    continue
                new_count += 1
                if len(samples) < 5:
                    samples.append(vessel)
            print(f"   Всего в PostgreSQL: {total_count}")
            print(f"   Новых для добавления: {new_count}")
            print("   Примеры первых 5 новых судов:")
            for vessel in samples:
                print(
                    f"   - MMSI: {vessel['mmsi']}, Имя: {vessel['name']}, Флаг: {vessel['flag']}"
                )
            print(f"   ... и ещё {max(new_count - len(samples), 0)} записей")
        else:
            print("💾 Добавление новых записей в SQLite...")
            total_count = 0
            added_count = 0
            failed_count = 0

            for vessel in iter_vessels_from_postgres(postgres_conn, batch_size=batch_size):
                total_count += 1
                if vessel["mmsi"] in existing_mmsi:
                    continue
                if insert_vessel_to_sqlite(sqlite_conn, vessel):
                    added_count += 1
                    existing_mmsi.add(vessel["mmsi"])
                else:
                    failed_count += 1

                if total_count % 1000 == 0:
                    print(
                        f"   Проверено {total_count} записей, добавлено {added_count}"
                    )

            # Фиксируем пакетную синхронизацию одной транзакцией,
            # чтобы избежать частично примененных данных при штатном сценарии.
            sqlite_conn.commit()

            print()
            print(f"✅ Завершено:")
            print(f"   Проверено: {total_count}")
            print(f"   ✓ Добавлено: {added_count}")
            print(f"   ✗ Ошибок: {failed_count}")

        postgres_conn.close()
        sqlite_conn.close()

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Синхронизация данных из PostgreSQL в SQLite"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, что будет сделано, без внесения изменений",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host PostgreSQL (по умолчанию из POSTGRES_HOST или localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Порт PostgreSQL (по умолчанию из POSTGRES_PORT или 5432)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Имя БД (по умолчанию из POSTGRES_DB или vessels_db)",
    )
    parser.add_argument(
        "--user",
        default=None,
        help="Пользователь PostgreSQL (по умолчанию из POSTGRES_USER или user)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Пароль PostgreSQL (по умолчанию из POSTGRES_PASSWORD)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Размер батча чтения из PostgreSQL (по умолчанию 1000)",
    )

    args = parser.parse_args()

    # Обновить конфиг из аргументов
    if args.host:
        POSTGRES_CONFIG["host"] = args.host
    if args.port:
        POSTGRES_CONFIG["port"] = args.port
    if args.db:
        POSTGRES_CONFIG["database"] = args.db
    if args.user:
        POSTGRES_CONFIG["user"] = args.user
    if args.password is not None:
        POSTGRES_CONFIG["password"] = args.password

    print(f"🚀 Начало синхронизации в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        sync_databases(dry_run=args.dry_run, batch_size=max(args.batch_size, 100))
        print()
        print(
            f"✨ Синхронизация завершена в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        print(f"❌ Синхронизация не удалась")
        exit(1)
