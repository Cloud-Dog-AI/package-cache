# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Cache key generation and hashing."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_json(obj: Any) -> str:
    """Produce a deterministic JSON representation for hashing."""
    if isinstance(obj, dict):
        return json.dumps(
            {k: _stable_json(v) for k, v in sorted(obj.items())}, sort_keys=True
        )
    if isinstance(obj, (list, tuple)):
        return json.dumps([_stable_json(v) for v in obj])
    if isinstance(obj, set):
        return json.dumps(sorted(str(v) for v in obj))
    return json.dumps(obj, default=str)


def cache_key(
    function_name: str,
    *,
    params: dict[str, Any] | None = None,
    context_hash: str = "",
    model_config_hash: str = "",
    prompt_hash: str = "",
) -> str:
    """Generate a deterministic cache key from function identity and input hashes.

    The key includes the function name, sorted input parameters, and optional
    hashes for context state, model configuration, and prompt templates. Any
    change in these components produces a different key, ensuring stale results
    are never served.
    """
    parts = [
        function_name,
        _stable_json(params or {}),
        context_hash,
        model_config_hash,
        prompt_hash,
    ]
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def hash_text(text: str) -> str:
    """Return a stable SHA-256 hex digest of the given text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_config(config: dict[str, Any]) -> str:
    """Return a stable hash of a configuration dict."""
    return hashlib.sha256(_stable_json(config).encode("utf-8")).hexdigest()
