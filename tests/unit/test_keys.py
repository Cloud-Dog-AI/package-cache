# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# Licensed under the Apache License, Version 2.0

"""Unit tests for cache key generation."""

from cloud_dog_cache.keys import cache_key, hash_text, hash_config


def test_deterministic_key():
    """Same inputs produce same key."""
    k1 = cache_key("fn", params={"a": 1, "b": 2})
    k2 = cache_key("fn", params={"b": 2, "a": 1})
    assert k1 == k2


def test_different_function_different_key():
    """Different function names produce different keys."""
    k1 = cache_key("fn1", params={"a": 1})
    k2 = cache_key("fn2", params={"a": 1})
    assert k1 != k2


def test_context_hash_changes_key():
    """Different context hashes produce different keys."""
    k1 = cache_key("fn", params={}, context_hash="abc")
    k2 = cache_key("fn", params={}, context_hash="def")
    assert k1 != k2


def test_model_config_changes_key():
    """Different model configs produce different keys."""
    k1 = cache_key("fn", params={}, model_config_hash="gpt4")
    k2 = cache_key("fn", params={}, model_config_hash="gpt3")
    assert k1 != k2


def test_hash_text():
    """hash_text produces deterministic SHA-256."""
    h1 = hash_text("hello world")
    h2 = hash_text("hello world")
    assert h1 == h2
    assert len(h1) == 64


def test_hash_config():
    """hash_config produces deterministic hash from dict."""
    h1 = hash_config({"model": "gpt4", "temperature": 0.7})
    h2 = hash_config({"temperature": 0.7, "model": "gpt4"})
    assert h1 == h2
