# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""CacheManager — orchestrates cache backends, logging, and statistics."""

from __future__ import annotations

import logging
from typing import Any, Optional

from cloud_dog_cache.backends.memory import MemoryCacheBackend
from cloud_dog_cache.models import CacheConfig, CacheEntry
from cloud_dog_cache.stats import CacheStats

logger = logging.getLogger(__name__)

_MANAGER: CacheManager | None = None


class CacheManager:
    """Central cache orchestrator.

    Wraps a pluggable backend with logging, config-driven enable/disable,
    and statistics collection.
    """

    def __init__(self, config: CacheConfig | None = None) -> None:
        """Initialise with configuration."""
        self.config = config or CacheConfig()
        self.backend = self._build_backend()

    def _build_backend(self) -> Any:
        """Instantiate the configured backend."""
        if self.config.backend == "redis" and self.config.redis_url:
            from cloud_dog_cache.backends.redis import RedisCacheBackend
            return RedisCacheBackend(redis_url=self.config.redis_url)
        return MemoryCacheBackend(max_entries=self.config.max_entries)

    @property
    def enabled(self) -> bool:
        """Return whether caching is active."""
        return self.config.enabled

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a cached value. Return None on miss or when disabled."""
        if not self.enabled:
            return None
        entry = await self.backend.get(key)
        if entry is None:
            logger.debug("cache_miss", extra={"key": key[:16]})
            return None
        logger.debug("cache_hit", extra={"key": key[:16]})
        return entry.value

    async def set(self, key: str, value: Any, *, ttl: int | None = None, tags: tuple[str, ...] = ()) -> None:
        """Store a value in the cache."""
        if not self.enabled:
            return
        effective_ttl = ttl if ttl is not None else self.config.ttl_seconds
        entry = CacheEntry(key=key, value=value, tags=tags)
        await self.backend.set(key, entry, effective_ttl)
        logger.debug("cache_set", extra={"key": key[:16], "ttl": effective_ttl})

    async def delete(self, key: str) -> None:
        """Remove a single cache entry."""
        await self.backend.delete(key)

    async def flush(self) -> None:
        """Remove all cache entries."""
        await self.backend.flush()
        logger.info("cache_flushed")

    async def stats(self) -> CacheStats:
        """Return current cache statistics."""
        return await self.backend.stats()


def init_cache(config: CacheConfig | None = None) -> CacheManager:
    """Initialise the global cache manager singleton."""
    global _MANAGER
    _MANAGER = CacheManager(config)
    return _MANAGER


def get_cache_manager() -> CacheManager | None:
    """Return the global cache manager, or None if not initialised."""
    return _MANAGER
