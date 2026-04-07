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
import sqlite3
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# Конфигурация подключений
POSTGRES_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "vessels_db",
    "user": "user",
    "password": "password",
}

# Путь к SQLite БД (относительный путь от скрипта)
SQLITE_DB_PATH = (
    Path(__file__).parent.parent
    / "База Данных PKS"
    / "ShipsDataBase"
    / "ships_database.sqb"
)


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


def get_vessels_from_postgres(postgres_conn):
    """Получить все судна из PostgreSQL для синхронизации."""
    cursor = postgres_conn.cursor(cursor_factory=RealDictCursor)
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
    vessels = cursor.fetchall()
    cursor.close()
    return vessels


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


def sync_databases(dry_run=False):
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

        # Получить существующие MMSI в SQLite
        print("📊 Анализ существующих MMSI в SQLite...")
        existing_mmsi = get_existing_mmsi_in_sqlite(sqlite_conn)
        print(f"   Найдено {len(existing_mmsi)} записей в SQLite")

        # Получить все судна из PostgreSQL
        print("📊 Загрузка данных из PostgreSQL...")
        vessels = get_vessels_from_postgres(postgres_conn)
        print(f"   Найдено {len(vessels)} записей в PostgreSQL")

        # Фильтровать только новые записи
        new_vessels = [v for v in vessels if v["mmsi"] not in existing_mmsi]
        print(f"   Из них {len(new_vessels)} новых записей для добавления")
        print()

        if not new_vessels:
            print("✅ Нет новых записей для добавления")
            postgres_conn.close()
            sqlite_conn.close()
            return

        if dry_run:
            print("🧪 DRY RUN - изменения не применяются")
            print("   Примеры первых 5 новых судов:")
            for vessel in new_vessels[:5]:
                print(
                    f"   - MMSI: {vessel['mmsi']}, Имя: {vessel['name']}, Флаг: {vessel['flag']}"
                )
            print(f"   ... и ещё {len(new_vessels) - 5} записей")
        else:
            print(f"💾 Добавление {len(new_vessels)} новых записей в SQLite...")

            added_count = 0
            failed_count = 0

            for i, vessel in enumerate(new_vessels, 1):
                if insert_vessel_to_sqlite(sqlite_conn, vessel):
                    added_count += 1
                else:
                    failed_count += 1

                if i % 1000 == 0:
                    print(
                        f"   Обработано {i}/{len(new_vessels)} ({i * 100 // len(new_vessels)}%)"
                    )

            # Фиксируем пакетную синхронизацию одной транзакцией,
            # чтобы избежать частично примененных данных при штатном сценарии.
            sqlite_conn.commit()

            print()
            print(f"✅ Завершено:")
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
        default=POSTGRES_CONFIG["host"],
        help=f"Host PostgreSQL (по умолчанию: {POSTGRES_CONFIG['host']})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=POSTGRES_CONFIG["port"],
        help=f"Порт PostgreSQL (по умолчанию: {POSTGRES_CONFIG['port']})",
    )
    parser.add_argument(
        "--db",
        default=POSTGRES_CONFIG["database"],
        help=f"Имя БД (по умолчанию: {POSTGRES_CONFIG['database']})",
    )
    parser.add_argument(
        "--user",
        default=POSTGRES_CONFIG["user"],
        help=f"Пользователь PostgreSQL (по умолчанию: {POSTGRES_CONFIG['user']})",
    )
    parser.add_argument(
        "--password", default=POSTGRES_CONFIG["password"], help="Пароль PostgreSQL"
    )

    args = parser.parse_args()

    # Обновить конфиг из аргументов
    POSTGRES_CONFIG.update(
        {
            "host": args.host,
            "port": args.port,
            "database": args.db,
            "user": args.user,
            "password": args.password,
        }
    )

    print(f"🚀 Начало синхронизации в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        sync_databases(dry_run=args.dry_run)
        print()
        print(
            f"✨ Синхронизация завершена в {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        print(f"❌ Синхронизация не удалась")
        exit(1)
        exit(1)
