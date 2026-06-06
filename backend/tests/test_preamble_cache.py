"""Tests for br8n.preamble_cache — the stdlib file cache for the session primer."""
from __future__ import annotations

import os
import time

import pytest


@pytest.fixture(autouse=True)
def cache_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("BR8N_PREAMBLE_CACHE_DIR", str(tmp_path))
    return tmp_path


def test_write_read_roundtrip():
    from br8n import preamble_cache

    preamble_cache.write("sess1", "proj", "dev", "<preamble>hi</preamble>")
    assert preamble_cache.read("sess1", "proj", "dev") == "<preamble>hi</preamble>"


def test_read_missing_returns_none():
    from br8n import preamble_cache

    assert preamble_cache.read("nope", "proj", "dev") is None


def test_invalidate_removes_all_sessions():
    from br8n import preamble_cache

    preamble_cache.write("s1", "proj", "dev", "a")
    preamble_cache.write("s2", "proj", "dev", "b")
    preamble_cache.invalidate("proj", "dev")
    assert preamble_cache.read("s1", "proj", "dev") is None
    assert preamble_cache.read("s2", "proj", "dev") is None


def test_invalidate_scoped_to_project_kb():
    from br8n import preamble_cache

    preamble_cache.write("s1", "proj", "dev", "a")
    preamble_cache.write("s1", "other", "dev", "b")
    preamble_cache.invalidate("proj", "dev")
    assert preamble_cache.read("s1", "proj", "dev") is None
    assert preamble_cache.read("s1", "other", "dev") == "b"


def test_malformed_file_reads_as_none(cache_dir):
    from br8n import preamble_cache

    path = cache_dir / f"{preamble_cache.cache_key('proj', 'dev')}.s1.json"
    path.write_text("not json{{{")
    assert preamble_cache.read("s1", "proj", "dev") is None


def test_prune_removes_old_keeps_fresh(cache_dir):
    from br8n import preamble_cache

    preamble_cache.write("old", "proj", "dev", "x")
    old_file = next(cache_dir.glob("*.json"))
    stale = time.time() - 100 * 3600
    os.utime(old_file, (stale, stale))
    preamble_cache.write("fresh", "proj", "dev", "y")  # write() triggers prune()
    assert preamble_cache.read("old", "proj", "dev") is None
    assert preamble_cache.read("fresh", "proj", "dev") == "y"
