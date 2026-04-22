# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Unit tests for the @cached decorator."""

import pytest
from cloud_dog_cache import cached, init_cache, get_cache_manager
from cloud_dog_cache.models import CacheConfig


@pytest.fixture(autouse=True)
def setup_cache():
    """Initialise a fresh cache for each test."""
    init_cache(
        CacheConfig(enabled=True, backend="memory", ttl_seconds=3600, max_entries=100)
    )
    yield
    manager = get_cache_manager()
    if manager:
        import asyncio

        asyncio.get_event_loop().run_until_complete(manager.flush())


call_count = 0


@cached(ttl=3600)
async def expensive_function(x: int, y: int) -> int:
    """Simulate an expensive computation."""
    global call_count
    call_count += 1
    return x + y


@pytest.mark.asyncio
async def test_caches_result():
    """Second call with same args returns cached result."""
    global call_count
    call_count = 0
    result1 = await expensive_function(1, 2)
    result2 = await expensive_function(1, 2)
    assert result1 == 3
    assert result2 == 3
    assert call_count == 1  # Only called once


@pytest.mark.asyncio
async def test_different_args_not_cached():
    """Different args call the function again."""
    global call_count
    call_count = 0
    await expensive_function(1, 2)
    await expensive_function(3, 4)
    assert call_count == 2


@pytest.mark.asyncio
async def test_disabled_cache_always_calls():
    """When cache is disabled, function is always called."""
    global call_count
    call_count = 0
    init_cache(CacheConfig(enabled=False))
    await expensive_function(1, 2)
    await expensive_function(1, 2)
    assert call_count == 2


@cached(ttl=3600, invalidate_on=["context_rebuild"])
async def context_sensitive(query: str) -> str:
    """Function tagged for context invalidation."""
    return f"result:{query}"


@pytest.mark.asyncio
async def test_invalidation_tag():
    """Entries with invalidation tags are flushed by tag."""
    await context_sensitive("hello")
    manager = get_cache_manager()
    stats_before = await manager.stats()
    assert stats_before.entries == 1

    await manager.backend.flush_by_tag("context_rebuild")
    stats_after = await manager.stats()
    assert stats_after.entries == 0
