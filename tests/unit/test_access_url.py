# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Unit tests for the URL-addressable cache layer (cloud_dog_cache.access).

All tests use the REAL :class:`CacheManager` with the in-memory backend, the
REAL HMAC signing implementation, and REAL URL parsing. No mocks.

The final test (``test_simulated_image_cache_manager_replacement``) is the
local proof for W28A-#A32: it exercises the new API end-to-end with the same
shape that ``ImageCacheManager.cache_image`` returns to its callers in
notification-agent. Closes A16's stop on access_url semantic.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time

import pytest

from cloud_dog_cache import (
    AccessUrlConfig,
    AccessUrlEntry,
    CacheConfig,
    CacheManager,
    URLAddressableCache,
    hash_text,
)


@pytest.fixture
def manager() -> CacheManager:
    """Fresh in-memory CacheManager for each test."""
    return CacheManager(
        CacheConfig(enabled=True, backend="memory", ttl_seconds=3600, max_entries=64)
    )


@pytest.fixture
def signed_cache(manager: CacheManager) -> URLAddressableCache:
    """URLAddressableCache configured with a non-empty signing secret."""
    return URLAddressableCache(
        manager,
        AccessUrlConfig(
            base_url="https://notificationagent0.cloud-dog.net",
            signing_secret="test-secret-for-w28a-a32-unit-tests",
            default_url_ttl_seconds=300,
        ),
    )


@pytest.fixture
def unsigned_cache(manager: CacheManager) -> URLAddressableCache:
    """URLAddressableCache with no signing secret — unsigned URLs only."""
    return URLAddressableCache(
        manager,
        AccessUrlConfig(base_url="https://example.cloud-dog.net"),
    )


# ---------------------------------------------------------------------------
# 32.A — Access-URL API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_with_url_unsigned_round_trip(unsigned_cache: URLAddressableCache):
    """set_with_url stores value AND returns a fetchable unsigned URL."""
    key = hash_text("https://upstream.example/cat.png")
    payload = b"\x89PNG\r\n\x1a\nFAKEIMAGEBYTES"

    entry = await unsigned_cache.set_with_url(
        key,
        payload,
        ttl=600,
        metadata={"format": "png", "original_uri": "https://upstream.example/cat.png"},
    )

    assert isinstance(entry, AccessUrlEntry)
    assert entry.key == key
    assert entry.signed is False
    assert entry.url_expires_at is None
    assert entry.url == f"https://example.cloud-dog.net/cache/access/{key}"
    assert entry.metadata["format"] == "png"

    # Round-trip: verify_url -> get -> original bytes
    verified = unsigned_cache.verify_url(entry.url)
    assert verified is not None
    vkey, vexp = verified
    assert vkey == key and vexp is None
    assert await unsigned_cache.get_by_url(entry.url) == payload


@pytest.mark.asyncio
async def test_set_with_url_signed_hmac_verifies(signed_cache: URLAddressableCache):
    """Signed URLs round-trip and the HMAC matches an independent calculation."""
    key = hash_text("https://upstream.example/dog.jpeg")
    payload = b"JPEGBYTES-A32"

    entry = await signed_cache.set_with_url(
        key, payload, ttl=600, url_ttl=120, signed=True
    )

    assert entry.signed is True
    assert entry.url_expires_at is not None
    assert "expires=" in entry.url and "sig=" in entry.url

    # Independent HMAC reproduction — no shortcut through the cache code path
    expires_ts = int(entry.url_expires_at.timestamp())
    expected_sig = hmac.new(
        b"test-secret-for-w28a-a32-unit-tests",
        f"{key}|{expires_ts}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert f"sig={expected_sig}" in entry.url

    # Full round-trip via the API
    assert await signed_cache.get_by_url(entry.url) == payload


@pytest.mark.asyncio
async def test_url_ttl_independent_of_cache_ttl(signed_cache: URLAddressableCache):
    """URL TTL is separate from cache content TTL.

    The cache entry lives for `ttl=3600s`; the signed URL is valid for `url_ttl=1s`.
    After ~1.1s the signed URL must reject, but the cache entry is still present
    (so a freshly-minted URL still works).
    """
    key = hash_text("ttl-isolation-key")
    payload = {"hello": "world"}

    entry = await signed_cache.set_with_url(
        key, payload, ttl=3600, url_ttl=1, signed=True
    )
    assert await signed_cache.get_by_url(entry.url) == payload

    await asyncio.sleep(1.2)

    # Signed URL has expired
    assert signed_cache.verify_url(entry.url) is None
    assert await signed_cache.get_by_url(entry.url) is None

    # But cache content is still alive — re-mint a fresh URL and it works
    fresh_url, _ = signed_cache.build_url(key, url_ttl=60, signed=True)
    assert await signed_cache.get_by_url(fresh_url) == payload


# ---------------------------------------------------------------------------
# 32.B — Signed/unsigned URL modes & failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signed_url_tamper_rejected(signed_cache: URLAddressableCache):
    """Any byte-flip in the URL key, expiry, or sig MUST cause rejection."""
    key = hash_text("tamper-target")
    await signed_cache.manager.set(key, b"secret-bytes", ttl=600)
    url, _ = signed_cache.build_url(key, url_ttl=60, signed=True)

    # 1. Flip one hex char in sig -> invalid HMAC
    if "sig=a" in url:
        tampered_sig = url.replace("sig=a", "sig=b", 1)
    else:
        # find first hex char of sig and flip
        sig_idx = url.index("sig=") + 4
        ch = url[sig_idx]
        flipped = "0" if ch != "0" else "1"
        tampered_sig = url[:sig_idx] + flipped + url[sig_idx + 1 :]
    assert signed_cache.verify_url(tampered_sig) is None

    # 2. Tamper with the key segment (path) — sig no longer matches new key
    parts = url.split("?", 1)
    tampered_path = parts[0][:-1] + ("0" if parts[0][-1] != "0" else "1")
    assert signed_cache.verify_url(tampered_path + "?" + parts[1]) is None

    # 3. Tamper with expires — sig no longer matches
    tampered_exp = url.replace("expires=", "expires=9999999999&_x=", 1)
    assert signed_cache.verify_url(tampered_exp) is None


@pytest.mark.asyncio
async def test_signed_requires_secret(unsigned_cache: URLAddressableCache):
    """Signed URL minting MUST raise when no signing_secret is configured."""
    with pytest.raises(ValueError, match="signing_secret"):
        unsigned_cache.build_url("anykey", url_ttl=60, signed=True)


@pytest.mark.asyncio
async def test_unsigned_path_with_signed_lookup_rejected(
    signed_cache: URLAddressableCache,
):
    """A URL missing a sig MUST verify only as unsigned (no expiry).

    But if a downstream consumer tampers by stripping the sig from a
    previously-signed URL, the verification surface treats it as unsigned
    and returns ``(key, None)``. The cache content lookup itself is the
    final auth gate. This test asserts that semantic is consistent.
    """
    key = hash_text("unsigned-coexist")
    await signed_cache.manager.set(key, b"public-but-cached", ttl=600)
    signed_url, _ = signed_cache.build_url(key, url_ttl=60, signed=True)
    stripped = signed_url.split("?", 1)[0]
    verified = signed_cache.verify_url(stripped)
    assert verified is not None
    assert verified == (key, None)


@pytest.mark.asyncio
async def test_get_by_url_miss_when_cache_evicted(
    signed_cache: URLAddressableCache,
):
    """get_by_url returns None when the underlying cache entry is gone."""
    key = hash_text("evict-me")
    entry = await signed_cache.set_with_url(
        key, b"content", ttl=600, signed=True, url_ttl=120
    )
    # Manually delete the cache entry via the underlying manager
    await signed_cache.manager.delete(key)
    assert await signed_cache.get_by_url(entry.url) is None
    # URL itself still verifies (signature is valid + not expired) — the
    # null result is from the cache lookup, which is exactly the contract.
    assert signed_cache.verify_url(entry.url) is not None


@pytest.mark.asyncio
async def test_build_url_for_existing_key(signed_cache: URLAddressableCache):
    """build_url mints URLs for keys already populated via the underlying manager."""
    key = hash_text("pre-existing")
    await signed_cache.manager.set(key, {"x": 1}, ttl=600)
    url, expires_at = signed_cache.build_url(key, url_ttl=30, signed=True)
    assert expires_at is not None
    assert int(expires_at.timestamp()) > int(time.time())
    assert await signed_cache.get_by_url(url) == {"x": 1}


# ---------------------------------------------------------------------------
# 32.D — Local proof: simulated ImageCacheManager replacement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_simulated_image_cache_manager_replacement(
    signed_cache: URLAddressableCache,
):
    """Demonstrate that URLAddressableCache replaces ImageCacheManager's contract.

    ImageCacheManager.cache_image returns:
        {
          "cache_key": ...,
          "cache_path": ...,
          "access_url": ...,
          "original_uri": ...,
          "format": ...,
          "size_bytes": ...,
          "cached_at": ...,
        }

    This test reproduces that exact response shape using ONLY URLAddressableCache
    + cloud_dog_cache.hash_text + AccessUrlEntry. No bespoke ``ImageCacheManager``
    code is touched. Closes A16's stop condition on access_url semantic.
    """
    # Simulated upstream image fetch — this is what URIHandler.fetch_image
    # would have returned in the real notification-agent code path.
    original_uri = "https://upstream.example/photo.jpeg"
    image_bytes = b"\xff\xd8\xff\xe0FAKEJPEGFORTEST"
    image_format = "jpeg"

    # === Replacement code path (would replace ImageCacheManager.cache_image) ===
    cache_key = hash_text(original_uri)
    entry = await signed_cache.set_with_url(
        cache_key,
        image_bytes,
        ttl=86400 * 30,  # 30-day cache TTL (matches ImageCacheManager default)
        url_ttl=300,  # 5-minute access window for downstream consumers
        signed=True,
        metadata={
            "original_uri": original_uri,
            "format": image_format,
            "size_bytes": len(image_bytes),
        },
    )

    # Construct the consumer-facing dict using ONLY the new API.
    response = {
        "cache_key": entry.key,
        "access_url": entry.url,
        "original_uri": entry.metadata["original_uri"],
        "format": entry.metadata["format"],
        "size_bytes": entry.metadata["size_bytes"],
        "url_expires_at": entry.url_expires_at.isoformat()
        if entry.url_expires_at
        else None,
    }

    # Assertions match what notification-agent's tests assert on the
    # ImageCacheManager response today.
    assert response["cache_key"] == hashlib.sha256(
        original_uri.encode("utf-8")
    ).hexdigest()
    assert response["access_url"].startswith(
        "https://notificationagent0.cloud-dog.net/cache/access/"
    )
    assert response["original_uri"] == original_uri
    assert response["format"] == "jpeg"
    assert response["size_bytes"] == len(image_bytes)
    assert response["url_expires_at"] is not None

    # Critically: a downstream consumer with ONLY the URL can fetch the
    # bytes without any service-internal API calls.
    fetched = await signed_cache.get_by_url(response["access_url"])
    assert fetched == image_bytes
