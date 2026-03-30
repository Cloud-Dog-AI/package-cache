# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Abstract cache backend protocol."""

from __future__ import annotations

from typing import Any, Optional, Protocol

from cloud_dog_cache.models import CacheEntry
from cloud_dog_cache.stats import CacheStats


class CacheBackend(Protocol):
    """Protocol for pluggable cache storage backends."""

    async def get(self, key: str) -> Optional[CacheEntry]:
        """Retrieve a cache entry by key. Return None if missing or expired."""
        ...

    async def set(self, key: str, entry: CacheEntry, ttl: int) -> None:
        """Store a cache entry with the given TTL in seconds."""
        ...

    async def delete(self, key: str) -> None:
        """Remove a single entry by key."""
        ...

    async def flush(self) -> None:
        """Remove all entries from the cache."""
        ...

    async def stats(self) -> CacheStats:
        """Return current cache statistics."""
        ...

    async def flush_by_tag(self, tag: str) -> int:
        """Remove all entries matching the given tag. Return count removed."""
        ...
