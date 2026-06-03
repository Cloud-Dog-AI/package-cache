# cloud_dog_cache

Platform caching package for LLM and tool call results.

## Quick Start

```python
from cloud_dog_cache import cached, init_cache, CacheConfig

# Initialise
init_cache(CacheConfig(enabled=True, backend="memory", ttl_seconds=3600))

# Decorate async functions
@cached(ttl=3600, invalidate_on=["context_rebuild"])
async def generate_sql(query: str, context_hash: str) -> str:
    ...
```

## Backends

- `memory` (default) — In-memory LRU with configurable max entries
- `redis` — Redis-backed with tag-based invalidation

## Invalidation

- TTL-based expiry
- Event-based: `invalidate_event("context_rebuild")`
- Manual: `await manager.flush()`
