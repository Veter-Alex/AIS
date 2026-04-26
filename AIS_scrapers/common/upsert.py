"""Общие SQL-фрагменты для upsert с приоритетом источников."""


def source_priority_sql(source_expr: str) -> str:
    """Вернуть SQL-выражение приоритета источника с fallback."""
    return (
        "COALESCE((SELECT priority FROM source_priority "
        f"WHERE source_name = {source_expr}), 999)"
    )
