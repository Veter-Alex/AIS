"""Нормализация числовых значений из HTML-текста."""

import re


def parse_int(value, min_digits: int = 1) -> int | None:
    """Извлечь целое число из строки с разделителями.

    Примеры:
    - "46,219 Tons" -> 46219
    - "Length: 399 m" -> 399
    - "-" -> None
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw == "-":
        return None

    digits = re.sub(r"[^0-9]", "", raw)
    if len(digits) < min_digits:
        return None
    return int(digits)
