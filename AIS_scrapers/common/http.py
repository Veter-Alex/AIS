"""Общие HTTP-утилиты c retry/backoff."""

import random
import time
from typing import Optional, Tuple

import requests


def fetch_page_with_retry(
    session: requests.Session,
    url: str,
    user_agents,
    timeout: int = 30,
    max_retries: int = 5,
    retry_base_delay: Optional[float] = None,
    retry_delay_range: Optional[Tuple[float, float]] = None,
    return_404_marker: bool = False,
):
    """Загрузить страницу с повторами и классификацией HTTP-ошибок."""
    for attempt in range(max_retries + 1):
        headers = {"User-Agent": random.choice(user_agents)}
        try:
            response = session.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code == 404 and return_404_marker:
                return "404_NOT_FOUND"
            retryable_http = status_code in {408, 409, 425, 429} or (
                status_code is not None and 500 <= status_code < 600
            )
            if not retryable_http or attempt >= max_retries:
                return None
        except Exception:
            if attempt >= max_retries:
                return None

        if retry_delay_range:
            delay = random.uniform(retry_delay_range[0], retry_delay_range[1])
        elif retry_base_delay:
            delay = retry_base_delay * (2**attempt)
        else:
            delay = 1.0 + attempt
        time.sleep(delay)

    return None

