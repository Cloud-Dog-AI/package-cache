# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""URL-addressable cache extension for cloud_dog_cache.

This module provides an additive layer on top of :class:`CacheManager` that
exposes cached entries via a URL — either an unsigned key path (relying on
upstream auth) or an HMAC-signed URL with embedded expiry (for tokenless
downstream consumers such as image renderers, e-mail bodies, or remote
notification clients).

It is the platform replacement for the bespoke ``access_url`` semantic
historically implemented by ``ImageCacheManager`` in
``notification-agent-mcp-server`` (see W28A-#A16-REPORT-2026-05-04 §2.B).

Key design properties:

* **Additive.** Pure new module. ``CacheManager`` is unchanged. Existing
  ``cached``/``init_cache``/``get_cache_manager`` consumers see no behaviour
  change.
* **TTL is independent.** The cache content TTL (how long the value lives in
  the cache backend) is separate from the URL TTL (how long a signed URL is
  valid). Callers can hold a long-lived cache entry but mint short-lived
  access URLs against it.
* **Two URL modes.** Unsigned URLs are simple ``{base}/cache/access/{key}``
  paths — the upstream caller is responsible for auth. Signed URLs append
  ``?expires=<unix_ts>&sig=<hex>`` and are HMAC-SHA256 verifiable without
  any per-request server lookup beyond the cache itself.
* **No new dependencies.** Uses only ``hmac``/``hashlib`` from stdlib.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, quote, urlsplit

from cloud_dog_cache.manager import CacheManager


# ---------------------------------------------------------------------------
# Configuration & data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccessUrlConfig:
    """Runtime configuration for the URL-addressable cache layer.

    Attributes:
        base_url: Public base URL where the cache router is mounted, e.g.
            ``https://notificationagent0.cloud-dog.net``. The access path
            ``/cache/access/{key}`` is appended.
        signing_secret: Secret used for HMAC-SHA256 signing. When empty,
            ``signed=True`` calls raise ``ValueError`` — services MUST
            provide a secret to mint signed URLs. Reading the secret from
            Vault and passing it here is the responsibility of the consuming
            service.
        default_url_ttl_seconds: Default validity window for signed URLs
            when caller does not specify ``url_ttl``.
        access_path_prefix: Path prefix appended to ``base_url`` to form
            the access URL. Defaults to ``"/cache/access"``.
    """

    base_url: str = ""
    signing_secret: str = ""
    default_url_ttl_seconds: int = 300
    access_path_prefix: str = "/cache/access"


@dataclass(frozen=True, slots=True)
class AccessUrlEntry:
    """A cache entry plus its mint URL metadata.

    Returned by :meth:`URLAddressableCache.set_with_url`. Mirrors the shape
    historically returned by ``ImageCacheManager.cache_image``:
    ``{cache_key, access_url, ...}``.
    """

    key: str
    url: str
    url_expires_at: Optional[datetime] = None
    signed: bool = False
    cache_ttl: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict view for JSON responses."""
        return {
            "cache_key": self.key,
            "access_url": self.url,
            "url_expires_at": (
                self.url_expires_at.isoformat() if self.url_expires_at else None
            ),
            "signed": self.signed,
            "cache_ttl_seconds": self.cache_ttl,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# URLAddressableCache
# ---------------------------------------------------------------------------


class URLAddressableCache:
    """Wraps a :class:`CacheManager` with URL-addressable access semantics.

    This class is the migration target for ``ImageCacheManager``: it stores
    a value in the cache and returns an externally-fetchable URL alongside
    the cache key.
    """

    def __init__(
        self,
        manager: CacheManager,
        config: AccessUrlConfig | None = None,
    ) -> None:
        """Initialise with a cache manager and access-URL configuration.

        Args:
            manager: An existing :class:`CacheManager` instance. The cache
                content lives here unchanged.
            config: URL-addressable configuration. If ``None``, a default
                with empty ``base_url`` and empty signing secret is used —
                the caller can still mint **relative** unsigned URLs but
                signed URLs will require an explicit secret.
        """
        self._manager = manager
        self._config = config or AccessUrlConfig()

    # ------------------------------------------------------------------
    # URL minting
    # ------------------------------------------------------------------

    def build_url(
        self,
        key: str,
        *,
        url_ttl: int | None = None,
        signed: bool = False,
    ) -> tuple[str, Optional[datetime]]:
        """Build an access URL for an existing cache key.

        This does NOT touch the cache backend — it only constructs the URL.
        Useful when the caller has already populated the cache via
        :meth:`CacheManager.set` and now wants an access URL for an
        existing key.

        Args:
            key: The cache key already present in the manager.
            url_ttl: URL validity window in seconds. Only meaningful when
                ``signed=True``. Defaults to ``config.default_url_ttl_seconds``.
            signed: When ``True``, append ``expires`` and ``sig`` query
                parameters (HMAC-SHA256). When ``False``, return a bare
                ``{base}/{prefix}/{key}`` URL — upstream auth is required.

        Returns:
            ``(url, url_expires_at)``. ``url_expires_at`` is ``None`` for
            unsigned URLs.

        Raises:
            ValueError: ``signed=True`` requested but no signing secret in
                config.
        """
        path = f"{self._config.access_path_prefix.rstrip('/')}/{quote(key, safe='')}"
        base = self._config.base_url.rstrip("/")
        if signed:
            if not self._config.signing_secret:
                raise ValueError(
                    "signed=True requested but AccessUrlConfig.signing_secret is empty"
                )
            ttl = (
                url_ttl
                if url_ttl is not None
                else self._config.default_url_ttl_seconds
            )
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            expires_ts = int(expires_at.timestamp())
            sig = self._sign(key, expires_ts)
            return (
                f"{base}{path}?expires={expires_ts}&sig={sig}",
                expires_at,
            )
        return f"{base}{path}", None

    async def set_with_url(
        self,
        key: str,
        value: Any,
        *,
        ttl: int | None = None,
        url_ttl: int | None = None,
        signed: bool = False,
        tags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> AccessUrlEntry:
        """Store a value AND mint an access URL for it.

        This is the canonical replacement for ``ImageCacheManager.cache_image``.

        Args:
            key: Cache key (typically a content hash — see
                :func:`cloud_dog_cache.keys.hash_text`).
            value: Cached value. Any type that the underlying backend can
                serialise (bytes, str, dict, etc.).
            ttl: Cache content TTL in seconds. ``None`` uses the manager's
                configured default.
            url_ttl: URL validity TTL in seconds (signed URLs only).
            signed: Whether to mint a signed URL.
            tags: Invalidation tags applied to the cache entry.
            metadata: Free-form metadata attached to the returned
                :class:`AccessUrlEntry` (e.g. content-type, original URI).
                NOT stored in the cache itself — this is a convenience for
                the caller's response shaping.

        Returns:
            :class:`AccessUrlEntry` with key, URL, expiry, and metadata.
        """
        await self._manager.set(key, value, ttl=ttl, tags=tags)
        url, expires_at = self.build_url(key, url_ttl=url_ttl, signed=signed)
        return AccessUrlEntry(
            key=key,
            url=url,
            url_expires_at=expires_at,
            signed=signed,
            cache_ttl=ttl,
            metadata=dict(metadata or {}),
        )

    # ------------------------------------------------------------------
    # URL verification & retrieval
    # ------------------------------------------------------------------

    def verify_url(self, url: str) -> Optional[tuple[str, Optional[datetime]]]:
        """Verify a signed or unsigned URL and return ``(key, expires_at)``.

        For unsigned URLs (no ``sig`` query param), this just extracts the
        key from the path. For signed URLs, this validates the HMAC and the
        expiry timestamp.

        Returns:
            ``(key, expires_at)`` on success, ``None`` on any failure
            (bad signature, expired, malformed path).
        """
        try:
            parts = urlsplit(url)
        except ValueError:
            return None
        prefix = self._config.access_path_prefix.rstrip("/")
        path = parts.path
        if prefix and not path.startswith(prefix + "/"):
            return None
        key_segment = path[len(prefix) + 1 :] if prefix else path.lstrip("/")
        if not key_segment:
            return None
        # urllib.parse.unquote — matches the quote() in build_url
        from urllib.parse import unquote

        key = unquote(key_segment)
        query = parse_qs(parts.query)
        sig_values = query.get("sig", [])
        if not sig_values:
            return (key, None)
        # Signed URL — validate
        expires_values = query.get("expires", [])
        if not expires_values:
            return None
        try:
            expires_ts = int(expires_values[0])
        except (TypeError, ValueError):
            return None
        if not self._config.signing_secret:
            return None
        expected = self._sign(key, expires_ts)
        if not hmac.compare_digest(expected, sig_values[0]):
            return None
        expires_at = datetime.fromtimestamp(expires_ts, tz=timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            return None
        return (key, expires_at)

    async def get_by_url(self, url: str) -> Optional[Any]:
        """Resolve a URL to its cached value.

        Returns ``None`` if the URL fails verification, has expired, or the
        cache key has been evicted/expired from the underlying manager.
        """
        verified = self.verify_url(url)
        if verified is None:
            return None
        key, _ = verified
        return await self._manager.get(key)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _sign(self, key: str, expires_ts: int) -> str:
        """HMAC-SHA256 over ``"{key}|{expires_ts}"``."""
        msg = f"{key}|{expires_ts}".encode("utf-8")
        secret = self._config.signing_secret.encode("utf-8")
        return hmac.new(secret, msg, hashlib.sha256).hexdigest()

    @property
    def manager(self) -> CacheManager:
        """The underlying :class:`CacheManager`."""
        return self._manager

    @property
    def config(self) -> AccessUrlConfig:
        """The active :class:`AccessUrlConfig`."""
        return self._config


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------


def create_access_url_router(
    cache: URLAddressableCache,
    *,
    media_type_resolver: Optional[Any] = None,
) -> Any:
    """Create a FastAPI router exposing ``GET {access_path_prefix}/{key}``.

    The router validates the URL (signature + expiry when present), looks
    up the cache entry, and returns the value. ``bytes``/``bytearray``
    values are returned as a binary ``Response`` (with optional
    ``media_type_resolver(key, value) -> str``); other values are returned
    as JSON.

    Args:
        cache: The :class:`URLAddressableCache` to serve from.
        media_type_resolver: Optional callable receiving ``(key, value)``
            and returning a content-type string for binary responses.

    Returns:
        A FastAPI ``APIRouter``.
    """
    from fastapi import APIRouter, HTTPException, Request, Response

    prefix = cache.config.access_path_prefix.rstrip("/")
    router = APIRouter(tags=["cache-access"])

    @router.get(prefix + "/{key:path}")
    async def access(key: str, request: Request) -> Response:
        # Reconstruct the URL exactly as a downstream consumer would have
        # received it, then verify against the live config.
        full_url = (
            f"{cache.config.base_url.rstrip('/')}{prefix}/{quote(key, safe='')}"
        )
        if request.url.query:
            full_url = f"{full_url}?{request.url.query}"
        verified = cache.verify_url(full_url)
        if verified is None:
            raise HTTPException(status_code=403, detail="invalid or expired url")
        verified_key, _ = verified
        value = await cache.manager.get(verified_key)
        if value is None:
            raise HTTPException(status_code=404, detail="cache miss")
        if isinstance(value, (bytes, bytearray)):
            content_type = (
                media_type_resolver(verified_key, value)
                if media_type_resolver is not None
                else "application/octet-stream"
            )
            return Response(content=bytes(value), media_type=content_type)
        # JSON fall-through
        from fastapi.responses import JSONResponse

        return JSONResponse(content=value)

    return router


__all__ = [
    "AccessUrlConfig",
    "AccessUrlEntry",
    "URLAddressableCache",
    "create_access_url_router",
]
