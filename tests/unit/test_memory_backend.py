# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Unit tests for the in-memory LRU cache backend."""

import asyncio
import pytest
from cloud_dog_cache.backends.memory import MemoryCacheBackend
from cloud_dog_cache.models import CacheEntry


@pytest.fixture
def backend():
    """Create a fresh memory backend."""
    return MemoryCacheBackend(max_entries=5)


@pytest.mark.asyncio
async def test_set_and_get(backend):
    """Store and retrieve a value."""
    entry = CacheEntry(key="k1", value="hello")
    await backend.set("k1", entry, ttl=60)
    result = await backend.get("k1")
    assert result is not None
    assert result.value == "hello"


@pytest.mark.asyncio
async def test_miss_returns_none(backend):
    """Missing key returns None."""
    assert await backend.get("nonexistent") is None


@pytest.mark.asyncio
async def test_ttl_expiry(backend):
    """Entry with zero TTL expires immediately."""
    entry = CacheEntry(key="k1", value="expired")
    await backend.set("k1", entry, ttl=0)
    # Sleep briefly so time passes
    await asyncio.sleep(0.01)
    assert await backend.get("k1") is None


@pytest.mark.asyncio
async def test_lru_eviction(backend):
    """Oldest entries evicted when max_entries reached."""
    for i in range(6):
        entry = CacheEntry(key=f"k{i}", value=i)
        await backend.set(f"k{i}", entry, ttl=3600)
    # k0 should have been evicted
    assert await backend.get("k0") is None
    assert (await backend.get("k5")).value == 5


@pytest.mark.asyncio
async def test_flush(backend):
    """Flush removes all entries."""
    for i in range(3):
        await backend.set(f"k{i}", CacheEntry(key=f"k{i}", value=i), ttl=3600)
    await backend.flush()
    stats = await backend.stats()
    assert stats.entries == 0


@pytest.mark.asyncio
async def test_flush_by_tag(backend):
    """Tag-based flush removes only tagged entries."""
    await backend.set("a", CacheEntry(key="a", value=1, tags=("ctx",)), ttl=3600)
    await backend.set("b", CacheEntry(key="b", value=2, tags=("other",)), ttl=3600)
    await backend.set("c", CacheEntry(key="c", value=3, tags=("ctx",)), ttl=3600)
    removed = await backend.flush_by_tag("ctx")
    assert removed == 2
    assert await backend.get("a") is None
    assert (await backend.get("b")).value == 2


@pytest.mark.asyncio
async def test_stats(backend):
    """Stats track hits, misses, entries."""
    await backend.set("k1", CacheEntry(key="k1", value="v"), ttl=3600)
    await backend.get("k1")  # hit
    await backend.get("k2")  # miss
    stats = await backend.stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.entries == 1
