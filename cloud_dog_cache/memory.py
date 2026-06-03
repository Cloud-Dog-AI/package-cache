# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Agent memory primitives — scoped namespaces, hierarchical TTL, tenant isolation.

W28B-305: Distributed memory on cloud_dog_cache. No new memory package.
"""

from __future__ import annotations

import enum
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

from cloud_dog_cache.manager import CacheManager, get_cache_manager


class MemoryScope(enum.Enum):
    """Hierarchical memory scopes with default TTL ordering.

    REQUEST < SESSION < USER_PROFILE < GLOBAL
    """

    REQUEST = "request"
    SESSION = "session"
    USER_PROFILE = "user_profile"
    GLOBAL = "global"


# Default TTL per scope (seconds). Callers can override.
DEFAULT_SCOPE_TTL: dict[MemoryScope, int] = {
    MemoryScope.REQUEST: 300,        # 5 minutes
    MemoryScope.SESSION: 3600,       # 1 hour
    MemoryScope.USER_PROFILE: 86400, # 24 hours
    MemoryScope.GLOBAL: 604800,      # 7 days
}


@dataclass(frozen=True, slots=True)
class MemoryNamespace:
    """A scoped, tenant-isolated namespace for agent memory.

    Keys are prefixed with ``mem:{tenant}:{scope}:{namespace}:`` to ensure
    isolation across tenants, scopes, and logical namespaces.
    """

    tenant_id: str
    scope: MemoryScope
    namespace: str = ""

    def _prefix(self) -> str:
        parts = ["mem", self.tenant_id, self.scope.value]
        if self.namespace:
            parts.append(self.namespace)
        return ":".join(parts) + ":"

    def full_key(self, key: str) -> str:
        """Return the fully-qualified cache key."""
        return f"{self._prefix()}{key}"

    def tag(self) -> str:
        """Return the invalidation tag for this namespace."""
        return self._prefix().rstrip(":")


@dataclass
class MemoryEntry:
    """A single memory entry with scope metadata."""

    key: str
    value: Any
    scope: MemoryScope
    tenant_id: str
    namespace: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryStore:
    """Agent memory store backed by CacheManager.

    Provides scoped get/set/list/clear operations with tenant isolation
    and hierarchical TTL defaults.
    """

    def __init__(
        self,
        tenant_id: str,
        *,
        manager: CacheManager | None = None,
        scope_ttl: dict[MemoryScope, int] | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._manager = manager
        self._scope_ttl = dict(DEFAULT_SCOPE_TTL)
        if scope_ttl:
            self._scope_ttl.update(scope_ttl)

    @property
    def manager(self) -> CacheManager:
        if self._manager is not None:
            return self._manager
        m = get_cache_manager()
        if m is None:
            raise RuntimeError("CacheManager not initialised; call init_cache() first")
        return m

    def _ns(self, scope: MemoryScope, namespace: str = "") -> MemoryNamespace:
        return MemoryNamespace(
            tenant_id=self._tenant_id,
            scope=scope,
            namespace=namespace,
        )

    def _ttl(self, scope: MemoryScope, ttl: int | None = None) -> int:
        if ttl is not None:
            return ttl
        return self._scope_ttl.get(scope, 3600)

    async def get(
        self,
        key: str,
        scope: MemoryScope = MemoryScope.SESSION,
        namespace: str = "",
    ) -> Any | None:
        """Retrieve a memory value by key and scope."""
        ns = self._ns(scope, namespace)
        return await self.manager.get(ns.full_key(key))

    async def set(
        self,
        key: str,
        value: Any,
        scope: MemoryScope = MemoryScope.SESSION,
        namespace: str = "",
        ttl: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a memory value with scope-appropriate TTL."""
        ns = self._ns(scope, namespace)
        effective_ttl = self._ttl(scope, ttl)
        # Wrap value with metadata for richer retrieval
        wrapped = {
            "v": value,
            "scope": scope.value,
            "tenant": self._tenant_id,
            "ns": namespace,
            "ts": time.time(),
        }
        if metadata:
            wrapped["meta"] = metadata
        await self.manager.set(
            ns.full_key(key),
            wrapped,
            ttl=effective_ttl,
            tags=(ns.tag(),),
        )

    async def delete(
        self,
        key: str,
        scope: MemoryScope = MemoryScope.SESSION,
        namespace: str = "",
    ) -> None:
        """Remove a single memory entry."""
        ns = self._ns(scope, namespace)
        await self.manager.delete(ns.full_key(key))

    async def clear_scope(
        self,
        scope: MemoryScope,
        namespace: str = "",
    ) -> int:
        """Clear all entries in a scope/namespace. Returns count removed."""
        ns = self._ns(scope, namespace)
        return await self.manager.backend.flush_by_tag(ns.tag())

    async def clear_tenant(self) -> int:
        """Clear all entries for this tenant across all scopes."""
        total = 0
        for scope in MemoryScope:
            total += await self.clear_scope(scope)
        return total


class VectorSearchAdapter:
    """Optional adapter for semantic search over memory entries.

    This is a protocol/interface — concrete implementations connect to
    index-retriever, Qdrant, ChromaDB, etc.
    """

    async def index(self, key: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Index a memory entry for semantic search."""
        raise NotImplementedError

    async def search(self, query: str, *, top_k: int = 5, filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Search memory entries by semantic similarity."""
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        """Remove a memory entry from the search index."""
        raise NotImplementedError
