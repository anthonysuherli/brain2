"""Activity-graph flow against a real local SQLiteStore.

Embeddings are stubbed (no network); the LLM task pass is disabled. Exercises the
full append path, the read surfaces (rollup/stats/query), and the cardinal
best-effort contract: a failing update must never raise.
"""

from __future__ import annotations

import pytest

import brain2.knowledge_graph.activity as act
from brain2.capture.models import WorkspaceSnapshot

DIM = 1536


@pytest.fixture
def local_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BRAIN2_ACTIVITY_LLM", "0")
    monkeypatch.setenv("BRAIN2_ACTIVITY_KG", "1")

    async def fake_embed(texts):
        return [[0.1] * DIM for _ in texts]

    monkeypatch.setattr(act, "embed_batch", fake_embed)
    # Fresh store for this db_path (the factory caches by path).
    from brain2 import store as store_mod

    store_mod._local_stores.clear()
    yield


def _snap(**kw) -> WorkspaceSnapshot:
    base = dict(
        project_path="/code/brain2",
        trigger="manual",
        captured_at="2026-05-30T10:00:00Z",
        branch="dev",
    )
    base.update(kw)
    return WorkspaceSnapshot(**base)


async def test_append_persists_and_dedupes_across_captures(local_env):
    await act._run_activity_update(_snap(hypothesis="port KG", cursor_file="store/base.py"), "f1")
    await act._run_activity_update(_snap(branch="main", hypothesis="fix bug"), "f2")

    stats = act.activity_stats()
    assert stats["node_count"] > 0
    # The repo node is shared across both captures; each capture is its own session.
    assert stats["by_type"]["repo"] == 1
    assert stats["by_type"]["session"] == 2


async def test_rollup_is_newest_first_and_cross_repo(local_env):
    await act._run_activity_update(_snap(hypothesis="a"), "f1")
    await act._run_activity_update(_snap(branch="main", hypothesis="b"), "f2")
    rollup = act.activity_rollup()
    assert len(rollup) == 2
    assert {r["branch"] for r in rollup} == {"dev", "main"}
    assert all(r["repo"] == "brain2" for r in rollup)


async def test_query_returns_subgraph_and_summary(local_env):
    await act._run_activity_update(
        _snap(hypothesis="port KG builder", cursor_file="store/base.py"), "f1"
    )
    seeded = await act.query_activity("storage layer")
    assert isinstance(seeded["nodes"], list) and seeded["nodes"]
    assert "Activity graph:" in seeded["summary"]

    whole = await act.query_activity()
    assert whole["nodes"]


async def test_repo_filter_narrows(local_env):
    await act._run_activity_update(_snap(hypothesis="x"), "f1")
    only = await act.query_activity(repo="brain2")
    assert all(
        (n.get("properties") or {}).get("repo") in (None, "brain2") or n.get("label") == "brain2"
        for n in only["nodes"]
    )
    empty = await act.query_activity(repo="does-not-exist")
    assert empty["nodes"] == []


async def test_empty_before_any_activity(local_env):
    assert act.activity_rollup() == []
    stats = act.activity_stats()
    assert stats["node_count"] == 0
    assert stats["hotspots"] == {"repos": [], "files": [], "tasks": []}


async def test_update_never_raises_on_failure(local_env, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("store down")

    monkeypatch.setattr(act, "resolve_activity_target", boom)
    # Best-effort contract: swallow everything. No raise == pass.
    await act._run_activity_update(_snap(), "f1")


def test_schedule_is_noop_when_disabled(local_env, monkeypatch):
    monkeypatch.setenv("BRAIN2_ACTIVITY_KG", "0")
    fired = {}

    async def fake_run(*a):
        fired["ran"] = True

    monkeypatch.setattr(act, "_run_activity_update", fake_run)
    act.schedule_activity_update(_snap(), "f1")
    assert "ran" not in fired
