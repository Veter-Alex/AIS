"""Проверки схемы БД перед стартом скрапера."""


def validate_scraper_schema(conn):
    """Проверить минимальные SQL-контракты для скраперов.

    Требования:
    - уникальность vessels.mmsi;
    - наличие scraper_state.scraper_name;
    - уникальность (scraper_name, mode) в scraper_state.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
             AND tc.table_schema = ccu.table_schema
            WHERE tc.table_name = 'vessels'
              AND tc.constraint_type = 'UNIQUE'
              AND ccu.column_name = 'mmsi'
            """
        )
        has_mmsi_unique = cur.fetchone()[0] > 0

        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_name = 'scraper_state' AND column_name = 'scraper_name'
            """
        )
        has_scraper_name = cur.fetchone()[0] > 0

        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = 'scraper_state'
              AND tc.constraint_type = 'UNIQUE'
            GROUP BY tc.constraint_name
            HAVING SUM(CASE WHEN kcu.column_name = 'scraper_name' THEN 1 ELSE 0 END) > 0
               AND SUM(CASE WHEN kcu.column_name = 'mode' THEN 1 ELSE 0 END) > 0
            """
        )
        has_state_unique = cur.fetchone() is not None

        if not has_mmsi_unique:
            raise RuntimeError(
                "Schema contract failed: vessels.mmsi must be UNIQUE for ON CONFLICT."
            )
        if not has_scraper_name:
            raise RuntimeError(
                "Schema contract failed: scraper_state.scraper_name column is required."
            )
        if not has_state_unique:
            raise RuntimeError(
                "Schema contract failed: scraper_state must have UNIQUE(scraper_name, mode)."
            )
    finally:
        cur.close()

