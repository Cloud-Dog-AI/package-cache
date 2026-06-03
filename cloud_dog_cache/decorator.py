# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""@cached decorator for transparent function result caching."""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Sequence

from cloud_dog_cache.keys import cache_key
from cloud_dog_cache.manager import get_cache_manager


def cached(
    *,
    ttl: int = 3600,
    invalidate_on: Sequence[str] = (),
    key_params: Sequence[str] | None = None,
    context_hash_param: str = "",
    model_config_hash_param: str = "",
    prompt_hash_param: str = "",
) -> Callable:
    """Decorator that caches async function results.

    Args:
        ttl: Time-to-live in seconds for cached entries.
        invalidate_on: Event names that trigger invalidation of this function's cache.
        key_params: Explicit parameter names to include in the cache key.
            If None, all parameters are included.
        context_hash_param: Name of the parameter containing the context hash.
        model_config_hash_param: Name of the parameter containing the model config hash.
        prompt_hash_param: Name of the parameter containing the prompt hash.

    Returns:
        A decorator that wraps async functions with caching logic.
    """

    def decorator(fn: Callable) -> Callable:
        fn_name = f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            manager = get_cache_manager()
            if manager is None or not manager.enabled:
                return await fn(*args, **kwargs)

            # Build parameter dict from function signature
            sig = inspect.signature(fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            all_params = dict(bound.arguments)

            # Select key params
            if key_params is not None:
                params = {k: all_params[k] for k in key_params if k in all_params}
            else:
                params = all_params

            # Extract hash params
            ctx_hash = (
                str(params.pop(context_hash_param, "")) if context_hash_param else ""
            )
            model_hash = (
                str(params.pop(model_config_hash_param, ""))
                if model_config_hash_param
                else ""
            )
            p_hash = str(params.pop(prompt_hash_param, "")) if prompt_hash_param else ""

            key = cache_key(
                fn_name,
                params=params,
                context_hash=ctx_hash,
                model_config_hash=model_hash,
                prompt_hash=p_hash,
            )

            # Check cache
            cached_value = await manager.get(key)
            if cached_value is not None:
                return cached_value

            # Execute and cache
            result = await fn(*args, **kwargs)
            tags = tuple(invalidate_on)
            await manager.set(key, result, ttl=ttl, tags=tags)
            return result

        wrapper.__cache_function_name__ = fn_name
        return wrapper

    return decorator
