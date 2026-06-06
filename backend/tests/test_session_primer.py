"""Tests for build_session_primer (and the capture cache-invalidation hook)."""
from __future__ import annotations

import hashlib

import pytest

DIM = 1536


def _fake_vec(text):
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


async def _fake_embed_text(text):
    return _fake_vec(text)


@pytest.fixture
def local_engine(monkeypatch, tmp_path):
    import br8n.store as store_pkg

    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "engine.db"))
    monkeypatch.setenv("BR8N_PREAMBLE_CACHE_DIR", str(tmp_path / "pcache"))
    store_pkg._local_stores.clear()

    import br8n.agent.preamble as preamble
    import br8n.capture.service as capture_service

    monkeypatch.setattr(capture_service, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(preamble, "embed_text", _fake_embed_text)
    yield store_pkg
    store_pkg._local_stores.clear()


def _snapshot(hypothesis):
    from br8n.capture.models import WorkspaceSnapshot

    return WorkspaceSnapshot(
        project_path="/tmp/proj",
        trigger="blur",
        captured_at="2026-05-29T12:00:00Z",
        branch="main",
        hypothesis=hypothesis,
    )


async def test_primer_includes_snapshot(local_engine):
    from br8n.agent.session_primer import build_session_primer
    from br8n.capture.service import persist_snapshot
    from br8n.interfaces.mcp.tenancy import resolve_tenant

    ctx = resolve_tenant("proj", "kb", create=True)
    await persist_snapshot(ctx, _snapshot("Tracking the flaky scheduler timeout"))

    primer = await build_session_primer("proj", "kb", "scheduler timeout")
    assert primer is not None
    assert "Tracking the flaky scheduler timeout" in primer
    assert "<recent-snapshots>" in primer


async def test_primer_none_for_empty_kb(local_engine):
    from br8n.agent.session_primer import build_session_primer
    from br8n.interfaces.mcp.tenancy import resolve_tenant

    resolve_tenant("empty", "kb", create=True)  # KB exists, but no findings/synopsis
    primer = await build_session_primer("empty", "kb", "anything")
    assert primer is None


async def test_primer_from_synopsis_only(local_engine):
    """Orientation via the synopsis arm alone — no snapshots, no query bands."""
    from br8n.agent.session_primer import build_session_primer
    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.store import get_store

    ctx = resolve_tenant("synp", "kb", create=True)
    get_store(ctx.access_token).upsert_synopsis(
        ctx.kb_id, [{"topic": "Caching", "gloss": "How the primer cache works"}], 1, "test-model"
    )

    primer = await build_session_primer("synp", "kb", None)
    assert primer is not None
    assert "<synopsis>" in primer
    assert "<recent-snapshots>" not in primer  # synopsis-only, no snapshots


async def test_capture_invalidates_primer_cache(local_engine):
    from br8n import preamble_cache
    from br8n.capture.service import persist_snapshot
    from br8n.interfaces.mcp.tenancy import resolve_tenant

    # Seed a cached primer for the repo+branch the snapshot targets
    # (_snapshot uses project_path="/tmp/proj" → basename "proj", branch="main").
    preamble_cache.write("sessX", "proj", "main", "<preamble>stale</preamble>")
    assert preamble_cache.read("sessX", "proj", "main") == "<preamble>stale</preamble>"

    ctx = resolve_tenant("proj", "kb", create=True)
    await persist_snapshot(ctx, _snapshot("new work landed"))

    assert preamble_cache.read("sessX", "proj", "main") is None  # invalidated by capture
