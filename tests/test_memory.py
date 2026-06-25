# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Tests for W28B-305 agent memory primitives."""

from __future__ import annotations

import pytest

from cloud_dog_cache import (
    CacheConfig,
    MemoryNamespace,
    MemoryScope,
    MemoryStore,
    DEFAULT_SCOPE_TTL,
    init_cache,
)


@pytest.fixture()
def manager():
    return init_cache(CacheConfig(enabled=True, backend="memory", max_entries=500))


@pytest.fixture()
def store(manager):
    return MemoryStore("tenant-1", manager=manager)


# ---------------------------------------------------------------------------
# MemoryNamespace
# ---------------------------------------------------------------------------


class TestMemoryNamespace:
    def test_full_key_with_namespace(self):
        ns = MemoryNamespace(tenant_id="t1", scope=MemoryScope.SESSION, namespace="agent-1")
        assert ns.full_key("foo") == "mem:t1:session:agent-1:foo"

    def test_full_key_without_namespace(self):
        ns = MemoryNamespace(tenant_id="t1", scope=MemoryScope.REQUEST)
        assert ns.full_key("bar") == "mem:t1:request:bar"

    def test_tag(self):
        ns = MemoryNamespace(tenant_id="t1", scope=MemoryScope.USER_PROFILE, namespace="ctx")
        assert ns.tag() == "mem:t1:user_profile:ctx"

    def test_tenant_isolation_different_keys(self):
        ns1 = MemoryNamespace(tenant_id="a", scope=MemoryScope.SESSION)
        ns2 = MemoryNamespace(tenant_id="b", scope=MemoryScope.SESSION)
        assert ns1.full_key("k") != ns2.full_key("k")

    def test_scope_isolation_different_keys(self):
        ns1 = MemoryNamespace(tenant_id="t", scope=MemoryScope.REQUEST)
        ns2 = MemoryNamespace(tenant_id="t", scope=MemoryScope.SESSION)
        assert ns1.full_key("k") != ns2.full_key("k")


# ---------------------------------------------------------------------------
# MemoryScope
# ---------------------------------------------------------------------------


class TestMemoryScope:
    def test_default_ttl_ordering(self):
        assert DEFAULT_SCOPE_TTL[MemoryScope.REQUEST] < DEFAULT_SCOPE_TTL[MemoryScope.SESSION]
        assert DEFAULT_SCOPE_TTL[MemoryScope.SESSION] < DEFAULT_SCOPE_TTL[MemoryScope.USER_PROFILE]
        assert DEFAULT_SCOPE_TTL[MemoryScope.USER_PROFILE] < DEFAULT_SCOPE_TTL[MemoryScope.GLOBAL]

    def test_all_scopes_have_ttl(self):
        for scope in MemoryScope:
            assert scope in DEFAULT_SCOPE_TTL


# ---------------------------------------------------------------------------
# MemoryStore — basic CRUD
# ---------------------------------------------------------------------------


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_set_and_get(self, store):
        await store.set("greeting", "hello", scope=MemoryScope.SESSION)
        result = await store.get("greeting", scope=MemoryScope.SESSION)
        assert result is not None
        assert result["v"] == "hello"
        assert result["scope"] == "session"
        assert result["tenant"] == "tenant-1"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, store):
        result = await store.get("nonexistent", scope=MemoryScope.SESSION)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, store):
        await store.set("temp", "value", scope=MemoryScope.REQUEST)
        await store.delete("temp", scope=MemoryScope.REQUEST)
        assert await store.get("temp", scope=MemoryScope.REQUEST) is None

    @pytest.mark.asyncio
    async def test_metadata_stored(self, store):
        await store.set("k", "v", scope=MemoryScope.SESSION, metadata={"source": "llm"})
        result = await store.get("k", scope=MemoryScope.SESSION)
        assert result["meta"] == {"source": "llm"}

    @pytest.mark.asyncio
    async def test_custom_ttl(self, store):
        await store.set("short", "v", scope=MemoryScope.SESSION, ttl=10)
        result = await store.get("short", scope=MemoryScope.SESSION)
        assert result is not None

    @pytest.mark.asyncio
    async def test_namespace_isolation(self, store):
        await store.set("k", "agent-a", scope=MemoryScope.SESSION, namespace="a")
        await store.set("k", "agent-b", scope=MemoryScope.SESSION, namespace="b")
        a = await store.get("k", scope=MemoryScope.SESSION, namespace="a")
        b = await store.get("k", scope=MemoryScope.SESSION, namespace="b")
        assert a["v"] == "agent-a"
        assert b["v"] == "agent-b"


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_different_tenants_isolated(self, manager):
        store_a = MemoryStore("tenant-a", manager=manager)
        store_b = MemoryStore("tenant-b", manager=manager)

        await store_a.set("secret", "a-value", scope=MemoryScope.SESSION)
        await store_b.set("secret", "b-value", scope=MemoryScope.SESSION)

        a = await store_a.get("secret", scope=MemoryScope.SESSION)
        b = await store_b.get("secret", scope=MemoryScope.SESSION)

        assert a["v"] == "a-value"
        assert b["v"] == "b-value"

    @pytest.mark.asyncio
    async def test_clear_tenant_does_not_affect_other(self, manager):
        store_a = MemoryStore("tenant-a", manager=manager)
        store_b = MemoryStore("tenant-b", manager=manager)

        await store_a.set("k", "a", scope=MemoryScope.SESSION)
        await store_b.set("k", "b", scope=MemoryScope.SESSION)

        await store_a.clear_tenant()

        assert await store_a.get("k", scope=MemoryScope.SESSION) is None
        assert (await store_b.get("k", scope=MemoryScope.SESSION))["v"] == "b"


# ---------------------------------------------------------------------------
# Scope clearing
# ---------------------------------------------------------------------------


class TestScopeClearing:
    @pytest.mark.asyncio
    async def test_clear_scope_removes_only_target(self, store):
        await store.set("req-k", "v", scope=MemoryScope.REQUEST)
        await store.set("sess-k", "v", scope=MemoryScope.SESSION)

        await store.clear_scope(MemoryScope.REQUEST)

        assert await store.get("req-k", scope=MemoryScope.REQUEST) is None
        assert (await store.get("sess-k", scope=MemoryScope.SESSION))["v"] == "v"

    @pytest.mark.asyncio
    async def test_clear_scope_with_namespace(self, store):
        await store.set("k", "v1", scope=MemoryScope.SESSION, namespace="a")
        await store.set("k", "v2", scope=MemoryScope.SESSION, namespace="b")

        await store.clear_scope(MemoryScope.SESSION, namespace="a")

        assert await store.get("k", scope=MemoryScope.SESSION, namespace="a") is None
        assert (await store.get("k", scope=MemoryScope.SESSION, namespace="b"))["v"] == "v2"
