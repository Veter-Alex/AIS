"""Общие HTTP-утилиты c retry/backoff."""

import logging
import random
import time
from typing import Callable, Optional, Tuple

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
    on_retry: Optional[Callable[[str, int, int, str], None]] = None,
):
    """Загрузить страницу с повторами и классификацией HTTP-ошибок."""
    for attempt in range(max_retries + 1):
        headers = {"User-Agent": random.choice(user_agents)}
        status_code = None
        retry_after_seconds: Optional[float] = None
        error_kind = "unknown"
        error_text = ""
        try:
            response = session.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            error_kind = f"http_{status_code}" if status_code is not None else "http_error"
            error_text = str(exc)
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
                logger.error(
                    "HTTP request окончательно отклонен url=%s status=%s attempt=%s/%s err=%s",
                    url,
                    status_code,
                    attempt + 1,
                    max_retries + 1,
                    error_text,
                )
                return None
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as exc:
            error_kind = "timeout"
            error_text = str(exc)
            logger.warning(
                "HTTP timeout url=%s attempt=%s/%s err=%s",
                url,
                attempt + 1,
                max_retries + 1,
                error_text,
            )
            if attempt >= max_retries:
                logger.error(
                    "HTTP timeout окончательно не восстановлен url=%s after=%s attempts",
                    url,
                    max_retries + 1,
                )
                return None
        except requests.exceptions.ConnectionError as exc:
            error_kind = "connection"
            error_text = str(exc)
            logger.warning(
                "HTTP connection error url=%s attempt=%s/%s err=%s",
                url,
                attempt + 1,
                max_retries + 1,
                error_text,
            )
            if attempt >= max_retries:
                logger.error(
                    "HTTP connection error окончательно не восстановлен url=%s after=%s attempts",
                    url,
                    max_retries + 1,
                )
                return None
        except Exception as exc:
            error_kind = "unexpected"
            error_text = str(exc)
            logger.warning(
                "HTTP unexpected error url=%s attempt=%s/%s err=%s",
                url,
                attempt + 1,
                max_retries + 1,
                error_text,
            )
            if attempt >= max_retries:
                logger.error(
                    "HTTP unexpected error окончательно не восстановлен url=%s after=%s attempts",
                    url,
                    max_retries + 1,
                    exc_info=True,
                )
                return None

        if retry_delay_range:
            delay = random.uniform(retry_delay_range[0], retry_delay_range[1])
        elif retry_base_delay:
            delay = min(retry_base_delay * (2**attempt), 30.0)
            if retry_after_seconds is not None:
                delay = max(delay, retry_after_seconds)
        else:
            # Базовая политика по типу ошибки.
            if error_kind == "timeout":
                delay = min(2.0 + attempt * 1.5, 20.0)
            elif error_kind == "connection":
                delay = min(1.0 + attempt * 1.0, 15.0)
            elif error_kind == "http_429":
                delay = max(8.0 + attempt * 2.0, retry_after_seconds or 0.0)
            elif error_kind.startswith("http_5"):
                delay = min(3.0 + attempt * 2.0, 30.0)
            else:
                delay = min(1.5 + attempt, 20.0)

        # Небольшой jitter, чтобы не биться в сервер синхронными волнами.
        delay = min(delay + random.uniform(0.1, 1.0), 45.0)
        logger.info("Retrying url=%s in %.2fs (%s)", url, delay, error_kind)
        if on_retry is not None:
            on_retry(url, attempt + 1, max_retries + 1, error_kind)
        time.sleep(delay)

    return None

