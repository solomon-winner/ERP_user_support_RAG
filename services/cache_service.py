"""
Cache Service — Redis-based caching for guide responses.

Caches:
  - Common guide queries
  - Route field descriptions
  - Process definitions
"""
import json
from typing import Optional, Any
from app.config import settings


class CacheService:
    """Simple Redis cache with in-memory fallback."""

    def __init__(self):
        self._redis = None
        self._memory_cache: dict = {}
        self._use_redis = False

    async def initialize(self) -> None:
        """Connect to Redis, fall back to in-memory if unavailable."""
        if not settings.CACHE_ENABLED:
            print("[Cache] Caching disabled")
            return

        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            self._use_redis = True
            print("[Cache] Connected to Redis")
        except Exception as e:
            print(f"[Cache] Redis unavailable ({e}). Using in-memory fallback.")
            self._use_redis = False

    async def get(self, key: str) -> Optional[str]:
        """Get a cached value by key."""
        if self._use_redis and self._redis:
            return await self._redis.get(key)
        return self._memory_cache.get(key)

    async def set(self, key: str, value: str, ttl: int = None) -> None:
        """Set a cached value with optional TTL."""
        ttl = ttl or settings.CACHE_TTL_SECONDS
        if self._use_redis and self._redis:
            await self._redis.set(key, value, ex=ttl)
        else:
            self._memory_cache[key] = value

    async def delete(self, key: str) -> None:
        """Delete a cached value."""
        if self._use_redis and self._redis:
            await self._redis.delete(key)
        elif key in self._memory_cache:
            del self._memory_cache[key]

    async def get_json(self, key: str) -> Optional[Any]:
        """Get a cached JSON value."""
        raw = await self.get(key)
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        return None

    async def set_json(self, key: str, value: Any, ttl: int = None) -> None:
        """Set a cached JSON value."""
        await self.set(key, json.dumps(value, default=str), ttl)

    async def cache_key(self, *parts: str) -> str:
        """Generate a cache key from parts."""
        return ":".join(parts)


# Singleton instance
cache_service = CacheService()
