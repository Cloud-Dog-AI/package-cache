# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Event-based cache invalidation hooks."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Well-known invalidation event names.
CONTEXT_REBUILD = "context_rebuild"
CONFIG_CHANGE = "config_change"
PROMPT_CHANGE = "prompt_change"
MANUAL_FLUSH = "manual_flush"


async def invalidate_event(event_name: str) -> int:
    """Fire an invalidation event, flushing cache entries tagged with *event_name*.

    Returns the number of entries removed.
    """
    from cloud_dog_cache.manager import get_cache_manager

    manager = get_cache_manager()
    if manager is None:
        return 0
    removed = await manager.backend.flush_by_tag(event_name)
    logger.info("cache_invalidation", extra={"event": event_name, "removed": removed})
    return removed
