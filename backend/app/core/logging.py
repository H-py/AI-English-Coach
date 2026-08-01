"""Logging configuration.

Configures the standard ``logging`` module with a uniform, human-readable
console format. All modules obtain loggers via :func:`get_logger` so that the
configuration is applied consistently.
"""

import logging
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging() -> None:
    """Initialise root logging with the project-wide format and level.

    Safe to call multiple times; subsequent calls are no-ops once handlers are
    attached.
    """
    level = logging.DEBUG if settings.APP_DEBUG else logging.INFO

    root = logging.getLogger()
    # Avoid attaching duplicate handlers on reload (e.g. uvicorn --reload).
    if not any(
        isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
        for h in root.handlers
    ):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
        root.addHandler(handler)
    root.setLevel(level)

    # Reduce noise from third-party libraries in development.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with the project format."""
    return logging.getLogger(name)
