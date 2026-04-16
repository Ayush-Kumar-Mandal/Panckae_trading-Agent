"""
Redis client wrapper. Falls back to in-memory storage if Redis is unavailable.
"""

from typing import Any, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class RedisClient:
    """
    Redis wrapper with graceful fallback to in-memory dict.
    Used for fast-access caching and optional pub/sub.
    """

    def __init__(self, host: str = "localhost", port: int = 6379, password: str = ""):
        self._memory_store: dict[str, str] = {}
        self._redis = None

        try:
            import redis
            self._redis = redis.Redis(
                host=host, port=port, password=password or None,
                decode_responses=True, socket_connect_timeout=2,
            )
            self._redis.ping()
            logger.info(f"Connected to Redis at {host}:{port}")
        except Exception:
            logger.info("Redis not available — using in-memory fallback")
            self._redis = None

    def get(self, key: str) -> Optional[str]:
        if self._redis:
            try:
                return self._redis.get(key)
            except Exception:
                pass
        return self._memory_store.get(key)

    def set(self, key: str, value: str, ttl: int = 0) -> None:
        if self._redis:
            try:
                if ttl > 0:
                    self._redis.setex(key, ttl, value)
                else:
                    self._redis.set(key, value)
                return
            except Exception:
                pass
        self._memory_store[key] = value

    def delete(self, key: str) -> None:
        if self._redis:
            try:
                self._redis.delete(key)
                return
            except Exception:
                pass
        self._memory_store.pop(key, None)

    @property
    def is_redis_connected(self) -> bool:
        return self._redis is not None
