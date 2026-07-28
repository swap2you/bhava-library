"""Structured logging setup."""

from __future__ import annotations

import logging
import re
from pathlib import Path

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SECRET_KEYS = ("password", "token", "secret", "authorization", "api_key")


class RedactingFilter(logging.Filter):
    """Strip emails and obvious secret-looking values from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = _EMAIL_RE.sub("[redacted-email]", msg)
        lowered = redacted.lower()
        for key in _SECRET_KEYS:
            if key in lowered:
                redacted = re.sub(
                    rf"({key}\s*[=:]\s*)\S+",
                    r"\1[redacted]",
                    redacted,
                    flags=re.IGNORECASE,
                )
        record.msg = redacted
        record.args = ()
        return True


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bhava")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = logging.FileHandler(logs_dir / "bhava.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(RedactingFilter())
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    console.addFilter(RedactingFilter())
    logger.addHandler(console)
    return logger


def get_logger(name: str = "bhava") -> logging.Logger:
    return logging.getLogger(name)
