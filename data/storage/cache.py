"""
Unified caching interface. Uses in-memory dict by default.
Can be upgraded to Redis by swapping the backend.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class CacheClient:
    """
    Simple in-memory cache with TTL support.
    Drop-in replacement for Redis in development.
    """

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expiry_timestamp)

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache. Returns None if expired or missing."""
        if key in self._store:
            value, expiry = self._store[key]
            if expiry == 0 or time.time() < expiry:
                return value
            else:
                del self._store[key]  # Expired
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 0) -> None:
        """Set a value in cache with optional TTL (0 = no expiry)."""
        expiry = time.time() + ttl_seconds if ttl_seconds > 0 else 0
        self._store[key] = (value, expiry)

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        if key in self._store:
            del self._store[key]
            return True
        return False

    async def get_or_set(self, key: str, factory, ttl_seconds: int = 0) -> Any:
        """Get from cache, or call factory() to compute and cache the value."""
        value = await self.get(key)
        if value is not None:
            return value
        value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
        await self.set(key, value, ttl_seconds)
        return value

    def clear(self) -> None:
        """Clear all cached data."""
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)
