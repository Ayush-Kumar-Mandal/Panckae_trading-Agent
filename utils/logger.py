"""
Centralized structured logging for the trading system.
All modules import `get_logger(__name__)` to get a module-scoped logger.
"""

import logging
import sys
import os
from datetime import datetime, timezone

# Force UTF-8 on Windows to avoid cp1252 encoding errors with emojis
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class TradingFormatter(logging.Formatter):
    """Custom formatter with timestamps, level, module, and message."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        color = self.COLORS.get(record.levelname, self.RESET)
        module = record.name.split(".")[-1] if record.name else "root"
        msg = record.getMessage()
        return (
            f"{color}[{ts}] [{record.levelname:<8}] [{module:<20}]{self.RESET} "
            f"{msg}"
        )


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger for the given module name."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(TradingFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger
