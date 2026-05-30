"""Read-surface API tests for the iOS companion v1 (local tier).

The native app needs two reads the desk surfaces never required:
  * GET /v1/resume/{project}/{kb}?format=json — structured resume, not HTML, so
    SwiftUI can lay it out natively.
  * GET /v1/projects — discovery: "what repos/branches do I have", since the
    phone (unlike the editor) doesn't already know its project + branch.

Both run against the real local engine (SQLiteStore) with only the embedder
faked, mirroring tests/test_engine_local.py.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

DIM = 1536


def _fake_vec(text: str) -> list[float]:
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
def local_api(monkeypatch, tmp_path):
    """Local backend + fresh DB + fake embedder; yields (TestClient, store_pkg)."""
    import brain2.store as store_pkg

    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "api.db"))
    store_pkg._local_stores.clear()

    import brain2.agent.preamble as preamble
    import brain2.capture.service as capture_service

    monkeypatch.setattr(capture_service, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(preamble, "embed_text", _fake_embed_text)

    from brain2.api.main import create_app

    client = TestClient(create_app())
    yield client, store_pkg
    store_pkg._local_stores.clear()


def _snapshot(hypothesis: str, branch: str = "main"):
    from brain2.capture.models import WorkspaceSnapshot

    return WorkspaceSnapshot(
        project_path="/tmp/proj",
        trigger="blur",
        captured_at="2026-05-29T12:00:00Z",
        branch=branch,
        git_diff_stat="1 file changed",
        open_files=["a.py"],
        cursor_file="a.py",
        cursor_line=10,
        terminal_tail="pytest",
        hypothesis=hypothesis,
    )


async def _seed_snapshot(project: str, kb: str, hypothesis: str) -> None:
    from brain2.capture.service import persist_snapshot
    from brain2.interfaces.mcp.tenancy import resolve_tenant

    ctx = resolve_tenant(project, kb, create=True)
    await persist_snapshot(ctx, _snapshot(hypothesis, branch=kb))


# --- JSON resume ------------------------------------------------------------


async def test_resume_json_format_returns_structured_card(local_api):
    client, _ = local_api
    await _seed_snapshot("proj", "main", "Tracking down the flaky scheduler timeout")

    res = client.get("/v1/resume/proj/main", params={"format": "json"})
    assert res.status_code == 200
    body = res.json()

    # Structured pieces the SwiftUI card lays out natively — NOT HTML.
    assert "card_html" not in body
    assert body["project"] == "proj"
    assert body["kb"] == "main"
    assert body["coverage"] in ("rich", "sparse", "gap")
    assert body["snapshot_count"] == 1
    assert body["hypothesis"] == "Tracking down the flaky scheduler timeout"
    assert isinstance(body["snapshots"], list)
    assert isinstance(body["synopsis"], list)
    assert isinstance(body["activity"], list)
    assert body["preamble"].startswith("<preamble>")


async def test_resume_default_format_is_html(local_api):
    """No format param → the existing HTML card (back-compat for the webview)."""
    client, _ = local_api
    await _seed_snapshot("proj", "main", "Investigating the cache bug")

    res = client.get("/v1/resume/proj/main")
    assert res.status_code == 200
    body = res.json()
    assert "card_html" in body
    assert body["card_html"].startswith("<html>")


# --- /v1/projects discovery -------------------------------------------------


async def test_projects_lists_repos_with_kbs(local_api):
    client, _ = local_api
    await _seed_snapshot("alpha", "main", "alpha work")
    await _seed_snapshot("alpha", "feature-x", "alpha feature work")
    await _seed_snapshot("beta", "main", "beta work")

    res = client.get("/v1/projects")
    assert res.status_code == 200
    projects = res.json()["projects"]

    by_name = {p["project"]: p for p in projects}
    assert set(by_name) == {"alpha", "beta"}

    alpha_kbs = {kb["kb"] for kb in by_name["alpha"]["kbs"]}
    assert alpha_kbs == {"main", "feature-x"}

    # Each KB carries the home-screen chips: last activity + snapshot count.
    alpha_main = next(kb for kb in by_name["alpha"]["kbs"] if kb["kb"] == "main")
    assert alpha_main["snapshot_count"] == 1
    assert alpha_main["last_activity"]  # a timestamp, not empty


def test_projects_empty_when_nothing_captured(local_api):
    client, _ = local_api
    res = client.get("/v1/projects")
    assert res.status_code == 200
    assert res.json()["projects"] == []


# --- cloud-tier gating ------------------------------------------------------


def test_projects_requires_auth_on_cloud(monkeypatch):
    """Cloud tier: no Bearer header → 401 from require_principal, before any
    Supabase call (so no creds/secret needed). Local tier ignores creds entirely;
    this proves the gate is live on cloud."""
    from brain2 import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("BRAIN2_BACKEND", "cloud")
    try:
        from brain2.api.main import create_app

        client = TestClient(create_app())
        res = client.get("/v1/projects")
        assert res.status_code == 401
    finally:
        monkeypatch.delenv("BRAIN2_BACKEND", raising=False)
        config.get_settings.cache_clear()
