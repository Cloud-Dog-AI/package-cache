# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""In-memory LRU cache backend with TTL support."""

from __future__ import annotations

import sys
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

from cloud_dog_cache.models import CacheEntry
from cloud_dog_cache.stats import CacheStats


class MemoryCacheBackend:
    """Thread-safe in-memory LRU cache with per-entry TTL and tag-based invalidation."""

    def __init__(self, *, max_entries: int = 1000) -> None:
        """Initialise with the given maximum entry count."""
        self._max_entries = max(1, max_entries)
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    async def get(self, key: str) -> Optional[CacheEntry]:
        """Retrieve an entry, promoting it in LRU order."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expired:
                del self._store[key]
                self._misses += 1
                return None
            self._store.move_to_end(key)
            self._hits += 1
            return entry

    async def set(self, key: str, entry: CacheEntry, ttl: int) -> None:
        """Store an entry with TTL. Evict oldest if at capacity."""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        stored = CacheEntry(
            key=entry.key,
            value=entry.value,
            created_at=entry.created_at,
            expires_at=expires_at,
            tags=entry.tags,
        )
        with self._lock:
            if key in self._store:
                del self._store[key]
            while len(self._store) >= self._max_entries:
                self._store.popitem(last=False)
                self._evictions += 1
            self._store[key] = stored

    async def delete(self, key: str) -> None:
        """Remove a single entry."""
        with self._lock:
            self._store.pop(key, None)

    async def flush(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()

    async def stats(self) -> CacheStats:
        """Return current statistics snapshot."""
        with self._lock:
            mem = sum(sys.getsizeof(e.value) for e in self._store.values())
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                entries=len(self._store),
                evictions=self._evictions,
                memory_bytes=mem,
            )

    async def flush_by_tag(self, tag: str) -> int:
        """Remove all entries with the given tag."""
        with self._lock:
            to_remove = [k for k, v in self._store.items() if tag in v.tags]
            for k in to_remove:
                del self._store[k]
            return len(to_remove)
