# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Runtime initialisation helper — reads cache config from cloud_dog_config."""

from __future__ import annotations

from typing import Any

from cloud_dog_cache.manager import CacheManager, init_cache
from cloud_dog_cache.models import CacheConfig


def init_cache_from_config(config: Any = None) -> CacheManager:
    """Initialise the global cache manager from cloud_dog_config.

    Reads ``cache.enabled``, ``cache.backend``, ``cache.ttl_seconds``,
    ``cache.max_entries``, ``cache.redis_url`` from the platform config.
    """
    if config is None:
        try:
            from cloud_dog_config import get_config
            config = get_config
        except ImportError:
            config = lambda key, default=None: default  # noqa: E731

    def _get(key: str, default: Any = None) -> Any:
        if callable(config):
            return config(key) or default
        return getattr(config, "get", lambda k, d=None: d)(key, default)

    cache_config = CacheConfig(
        enabled=_to_bool(_get("cache.enabled", True)),
        backend=str(_get("cache.backend", "memory") or "memory"),
        ttl_seconds=_to_int(_get("cache.ttl_seconds", 3600)),
        max_entries=_to_int(_get("cache.max_entries", 1000)),
        redis_url=str(_get("cache.redis_url", "") or ""),
    )
    return init_cache(cache_config)


def _to_bool(value: Any) -> bool:
    """Coerce a config value to bool."""
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: Any) -> int:
    """Coerce a config value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
