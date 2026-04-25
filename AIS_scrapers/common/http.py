"""Общие HTTP-утилиты c retry/backoff."""

import logging
import random
import time
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)


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
        status_code = None
        retry_after_seconds: Optional[float] = None
        try:
            response = session.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code == 429 and exc.response is not None:
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    retry_after_seconds = float(retry_after)
            logger.warning(
                "HTTP retryable check failed url=%s attempt=%s/%s status=%s",
                url,
                attempt + 1,
                max_retries + 1,
                status_code,
            )
            if status_code == 404 and return_404_marker:
                return "404_NOT_FOUND"
            retryable_http = status_code in {408, 409, 425, 429} or (
                status_code is not None and 500 <= status_code < 600
            )
            if not retryable_http or attempt >= max_retries:
                return None
        except Exception:
            logger.warning(
                "HTTP request failed url=%s attempt=%s/%s",
                url,
                attempt + 1,
                max_retries + 1,
                exc_info=True,
            )
            if attempt >= max_retries:
                return None

        if retry_delay_range:
            delay = random.uniform(retry_delay_range[0], retry_delay_range[1])
        elif retry_base_delay:
            delay = min(retry_base_delay * (2**attempt), 30.0)
            if retry_after_seconds is not None:
                delay = max(delay, retry_after_seconds)
        else:
            delay = 1.0 + attempt
        logger.info("Retrying url=%s in %.2fs", url, delay)
        time.sleep(delay)

    return None

