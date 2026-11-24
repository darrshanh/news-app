from abc import ABC, abstractmethod
from typing import Optional
import os
import logging
import redis

logger = logging.getLogger(__name__)

class BaseCache(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        pass

    @abstractmethod
    def set(self, key: str, value: bytes, ttl_seconds: int = 86400) -> None:
        pass

class InMemoryCache(BaseCache):
    def __init__(self, max_entries: int = 100):
        self._store: dict[str, bytes] = {}
        self.max_entries = max_entries

    def get(self, key: str) -> Optional[bytes]:
        value = self._store.get(key)
        if value is not None:
            # Refresh LRU position
            self._store[key] = self._store.pop(key)
        return value

    def set(self, key: str, value: bytes, ttl_seconds: int = 86400) -> None:
        if key in self._store:
            self._store.pop(key)
        elif len(self._store) >= self.max_entries:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
        self._store[key] = value

class RedisCache(BaseCache):
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.client = redis.Redis(host=host, port=port, db=db)
        self.client.ping()

    def get(self, key: str) -> Optional[bytes]:
        return self.client.get(key)

    def set(self, key: str, value: bytes, ttl_seconds: int = 86400) -> None:
        self.client.setex(key, ttl_seconds, value)

def get_cache_backend() -> BaseCache:
    use_redis = os.getenv("USE_REDIS", "false").lower() in ("true", "1", "yes")

    if use_redis:
        try:
            cache = RedisCache()
            logger.info("[*] Cache initialized: Using Redis at localhost:6379")
            return cache
        except Exception as e:
            logger.warning(f"[-] Redis connection failed ({e}). Falling back to InMemoryCache.")
    logger.info("[*] Cache initialized: Using In-Memory dictionary cache.")
    return InMemoryCache()