"""
Shared utility functions used across the trading system.
"""

import asyncio
import time
from decimal import Decimal
from functools import wraps
from typing import Any, Callable


def to_wei(amount: float, decimals: int = 18) -> int:
    """Convert a human-readable token amount to its smallest unit (wei)."""
    return int(Decimal(str(amount)) * Decimal(10 ** decimals))


def from_wei(amount: int, decimals: int = 18) -> float:
    """Convert from smallest unit (wei) back to human-readable amount."""
    return float(Decimal(str(amount)) / Decimal(10 ** decimals))


def format_address(address: str) -> str:
    """Return a shortened address for display: 0x1234...abcd."""
    if len(address) < 10:
        return address
    return f"{address[:6]}...{address[-4:]}"


def timestamp_now() -> float:
    """Return current UTC timestamp as float."""
    return time.time()


def timestamp_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division that returns default on zero denominator."""
    if denominator == 0:
        return default
    return numerator / denominator


async def retry_async(
    coro_func: Callable,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Any:
    """Retry an async function with exponential backoff."""
    last_exc = None
    current_delay = delay
    for attempt in range(1, max_retries + 1):
        try:
            return await coro_func()
        except exceptions as e:
            last_exc = e
            if attempt < max_retries:
                await asyncio.sleep(current_delay)
                current_delay *= backoff
    raise last_exc


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(value, max_val))
