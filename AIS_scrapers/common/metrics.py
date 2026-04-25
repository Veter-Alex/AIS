"""Простые runtime-метрики для логов скраперов."""

from dataclasses import dataclass


@dataclass
class RuntimeMetrics:
    pages_ok: int = 0
    pages_failed: int = 0
    vessels_parsed: int = 0
    vessels_saved: int = 0
    retry_count: int = 0
    photo_success: int = 0
    photo_attempts: int = 0

    def snapshot(self) -> str:
        photo_rate = (
            f"{(self.photo_success / self.photo_attempts) * 100:.1f}%"
            if self.photo_attempts
            else "n/a"
        )
        return (
            f"pages_ok={self.pages_ok} pages_failed={self.pages_failed} "
            f"vessels_parsed={self.vessels_parsed} vessels_saved={self.vessels_saved} "
            f"retry_count={self.retry_count} photo_success_rate={photo_rate}"
        )

