"""Tests for the curated doc-tree distiller (taxonomy inference + writer)."""
from __future__ import annotations

import hashlib

import pytest

from br8n.livingdocs.distill import plan_layout

DIM = 1536


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


def test_flat_until_min_notes():
    notes = [{"title": f"n{i}", "topic": None} for i in range(3)]
    layout = plan_layout(notes, cluster_min_notes=5, schema=None)
    assert all(entry["folder"] == "" for entry in layout)  # flat


def test_clusters_when_enough_and_topics_present():
    notes = [{"title": "auth race", "topic": "auth"} for _ in range(3)] + \
            [{"title": "ui tweak", "topic": "ui"} for _ in range(3)]
    layout = plan_layout(notes, cluster_min_notes=5, schema=None)
    folders = {e["folder"] for e in layout}
    assert "auth" in folders and "ui" in folders


def test_schema_overrides_inferred():
    notes = [{"title": "x", "topic": "auth"}]
    layout = plan_layout(notes, cluster_min_notes=1, schema=["security", "ui"])
    assert all(e["folder"] in {"security", "ui", ""} for e in layout)


@pytest.mark.asyncio
async def test_distill_writes_note_content_not_just_title(tmp_path, monkeypatch):
    """run_distill must render each note's full body, not just the H1 title.

    list_findings is a list view that omits `content`; the distiller has to fetch
    each finding's full record. This is the regression guard for that bug.
    """
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BR8N_LIVING_DOCS_LLM", "0")  # deterministic → flat layout

    import br8n.livingdocs.notes as notes_mod
    import br8n.store as store_pkg

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.distill import run_distill
    from br8n.livingdocs.notes import persist_note
    from br8n.livingdocs.paths import DocPaths

    ctx = resolve_tenant("proj", "main", create=True)

    body_one = "Chose SQLite over Postgres for the local tier; FTS via sqlite-vec."
    body_two = "Resume card routes on coverage band; gap → explore pipeline."
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content=f"# Storage choice\n\n{body_one}",
        session_id="s1", title="Storage choice",
    )
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content=f"# Resume routing\n\n{body_two}",
        session_id="s2", title="Resume routing",
    )

    res = await run_distill(ctx, project_path=str(tmp_path), kb="main")
    assert res["doc_count"] == 2

    docs_dir = DocPaths(project_path=str(tmp_path), kb="main").docs_dir
    blob = "\n".join(p.read_text() for p in docs_dir.rglob("*.md"))
    # The bug: bodies were empty (only the H1 title was written).
    assert body_one in blob
    assert body_two in blob

    store_pkg._local_stores.clear()
