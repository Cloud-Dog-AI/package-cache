# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""cloud_dog_cache — Platform caching package for LLM and tool call results.

Provides a transparent caching layer with configurable TTL, pluggable backends
(in-memory LRU, Redis), and event-based invalidation for context rebuilds,
config changes, and prompt template changes.

Usage::

    from cloud_dog_cache import cached, CacheManager, get_cache_manager

    @cached(ttl=3600, invalidate_on=["context_rebuild"])
    async def generate_sql(query: str, context_hash: str, model: str) -> str:
        ...

    # Manual access
    manager = get_cache_manager()
    await manager.flush()
    stats = await manager.stats()
"""

from cloud_dog_cache.manager import CacheManager, get_cache_manager, init_cache
from cloud_dog_cache.decorator import cached
from cloud_dog_cache.keys import cache_key, hash_text, hash_config
from cloud_dog_cache.stats import CacheStats
from cloud_dog_cache.models import CacheConfig, CacheEntry
from cloud_dog_cache.invalidation import invalidate_event
from cloud_dog_cache.runtime import init_cache_from_config
from cloud_dog_cache.api import create_cache_router

__all__ = [
    "CacheConfig",
    "CacheEntry",
    "CacheManager",
    "CacheStats",
    "cached",
    "cache_key",
    "create_cache_router",
    "get_cache_manager",
    "hash_config",
    "hash_text",
    "init_cache",
    "init_cache_from_config",
    "invalidate_event",
]
