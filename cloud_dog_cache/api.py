# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""FastAPI router for cache statistics and management endpoints."""

from __future__ import annotations

from typing import Any

from cloud_dog_cache.manager import get_cache_manager


def create_cache_router() -> Any:
    """Create a FastAPI APIRouter with /cache/stats and /cache/flush endpoints."""
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/cache", tags=["cache"])

    @router.get("/stats")
    async def cache_stats() -> dict[str, object]:
        """Return current cache statistics."""
        manager = get_cache_manager()
        if manager is None:
            return {"enabled": False, "stats": {}}
        stats = await manager.stats()
        return {"enabled": manager.enabled, "stats": stats.to_dict()}

    @router.post("/flush")
    async def cache_flush() -> dict[str, str]:
        """Flush all cache entries."""
        manager = get_cache_manager()
        if manager is None:
            raise HTTPException(status_code=503, detail="Cache not initialised")
        await manager.flush()
        return {"status": "flushed"}

    return router
