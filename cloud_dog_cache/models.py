# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Cache entry and configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """A single cached result with metadata."""

    key: str
    value: Any
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    hit_count: int = 0
    tags: tuple[str, ...] = ()

    @property
    def expired(self) -> bool:
        """Return True if this entry has passed its TTL."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at


@dataclass(frozen=True, slots=True)
class CacheConfig:
    """Runtime cache configuration."""

    enabled: bool = True
    backend: str = "memory"
    ttl_seconds: int = 3600
    max_entries: int = 1000
    max_memory_mb: int = 256
    redis_url: str = ""
