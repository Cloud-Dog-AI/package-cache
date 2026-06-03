# Changelog

## 0.2.0 (2026-05-04)

- **NEW: URL-addressable cache layer** (`cloud_dog_cache.access`)
  - `URLAddressableCache` wraps a `CacheManager` to expose cache entries via
    externally-fetchable URLs. Closes the architectural gap surfaced by W28A
    #A16 (notification-agent's `ImageCacheManager` had no platform replacement
    for its `access_url` semantic).
  - `AccessUrlConfig` — `base_url`, `signing_secret`, `default_url_ttl_seconds`,
    `access_path_prefix`.
  - `AccessUrlEntry` — return shape for `set_with_url`, mirrors the historical
    `ImageCacheManager.cache_image` response keys (cache_key, access_url, etc.).
  - Two URL modes: **unsigned** (`{base}/cache/access/{key}` — assumes upstream
    auth) and **signed** (HMAC-SHA256 over `key|expires_ts`, expiry verified
    server-side at fetch time).
  - URL TTL is independent of cache content TTL — long-lived cache entries can
    mint short-lived signed URLs.
  - `create_access_url_router(cache, *, media_type_resolver=None)` —
    drop-in FastAPI router serving `GET {prefix}/{key}` with signature +
    expiry validation.
- Pure additive change. No existing API surface modified. Backward compatible
  with all 0.1.x consumers.

## 0.1.1

- Patch release.

## 0.1.0 (2026-03-27)

- Initial release
- In-memory LRU backend with TTL
- Redis backend (optional)
- @cached decorator for async functions
- Event-based invalidation (context_rebuild, config_change, prompt_change)
- Tag-based flush
- CacheStats model
