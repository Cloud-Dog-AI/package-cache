# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Cache statistics model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CacheStats:
    """Snapshot of cache performance metrics."""

    hits: int = 0
    misses: int = 0
    entries: int = 0
    evictions: int = 0
    memory_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Return the cache hit rate as a fraction (0.0–1.0)."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, object]:
        """Serialise to a plain dict for health/stats endpoints."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "entries": self.entries,
            "evictions": self.evictions,
            "memory_bytes": self.memory_bytes,
            "hit_rate": round(self.hit_rate, 4),
        }
