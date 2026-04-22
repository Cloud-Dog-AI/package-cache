# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Redis cache backend (optional — requires ``redis`` package)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from cloud_dog_cache.models import CacheEntry
from cloud_dog_cache.stats import CacheStats


class RedisCacheBackend:
    """Redis-backed cache with TTL and tag-based invalidation.

    Requires the ``redis`` package: ``pip install redis``.
    """

    def __init__(self, *, redis_url: str, key_prefix: str = "cdc:") -> None:
        """Initialise with Redis connection URL."""
        import redis.asyncio as aioredis

        self._client = aioredis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def _tag_key(self, tag: str) -> str:
        return f"{self._prefix}tag:{tag}"

    async def get(self, key: str) -> Optional[CacheEntry]:
        """Retrieve a cached entry from Redis."""
        raw = await self._client.get(self._key(key))
        if raw is None:
            self._misses += 1
            return None
        data = json.loads(raw)
        self._hits += 1
        return CacheEntry(
            key=key,
            value=data["value"],
            created_at=datetime.fromisoformat(data["created_at"]),
            tags=tuple(data.get("tags", ())),
        )

    async def set(self, key: str, entry: CacheEntry, ttl: int) -> None:
        """Store a cache entry in Redis with TTL."""
        data = {
            "value": entry.value,
            "created_at": entry.created_at.isoformat(),
            "tags": list(entry.tags),
        }
        pipe = self._client.pipeline()
        pipe.setex(self._key(key), ttl, json.dumps(data, default=str))
        for tag in entry.tags:
            pipe.sadd(self._tag_key(tag), key)
            pipe.expire(self._tag_key(tag), ttl)
        await pipe.execute()

    async def delete(self, key: str) -> None:
        """Remove a single entry from Redis."""
        await self._client.delete(self._key(key))

    async def flush(self) -> None:
        """Remove all entries with the configured prefix."""
        keys = []
        async for key in self._client.scan_iter(match=f"{self._prefix}*"):
            keys.append(key)
        if keys:
            await self._client.delete(*keys)

    async def stats(self) -> CacheStats:
        """Return statistics (approximate for Redis)."""
        count = 0
        async for _ in self._client.scan_iter(match=f"{self._prefix}*"):
            count += 1
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            entries=count,
            evictions=self._evictions,
        )

    async def flush_by_tag(self, tag: str) -> int:
        """Remove all entries tagged with the given tag."""
        members = await self._client.smembers(self._tag_key(tag))
        removed = 0
        if members:
            pipe = self._client.pipeline()
            for member in members:
                pipe.delete(self._key(member))
            await pipe.execute()
            removed = len(members)
            await self._client.delete(self._tag_key(tag))
        return removed
