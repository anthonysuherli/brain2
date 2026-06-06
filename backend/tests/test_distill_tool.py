"""Local-tier test for the br8n_distill MCP tool (_distill_impl).

`force=True` runs run_distill immediately and returns {distilled, doc_count, folders};
`force=False` nudges the debounced background distiller and returns the scheduled shape.

Mirrors test_livingdocs_distill.py monkeypatch mechanics: BR8N_BACKEND=local + a tmp
BR8N_DB_PATH wire the real SQLiteStore; only the embedder is faked (no OpenAI) and the
synopsis rebuild is a no-op (no Anthropic). LLM topic inference is gated off so the
layout is deterministic + flat.
"""

from __future__ import annotations

import hashlib

import pytest

DIM = 1536


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


@pytest.mark.asyncio
async def test_distill_force_writes_docs(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BR8N_LIVING_DOCS_LLM", "0")  # deterministic → flat layout

    import br8n.livingdocs.notes as notes_mod
    import br8n.store as store_pkg

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    from br8n.interfaces.mcp import server
    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.livingdocs.paths import DocPaths

    ctx = resolve_tenant("proj", "main", create=True)
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# Storage choice\n\nChose SQLite over Postgres for the local tier.",
        session_id="s1", title="Storage choice",
    )
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# Resume routing\n\nResume card routes on coverage band.",
        session_id="s2", title="Resume routing",
    )

    res = await server._distill_impl("proj", "main", str(tmp_path), force=True)

    assert res["distilled"] is True
    assert res["forced"] is True
    assert res["doc_count"] >= 1
    assert res["project"] == "proj"
    assert res["kb"] == "main"

    docs_dir = DocPaths(project_path=str(tmp_path), kb="main").docs_dir
    md_files = list(docs_dir.rglob("*.md"))
    assert md_files, "force distill should write markdown files under .br8n/docs/"

    store_pkg._local_stores.clear()


@pytest.mark.asyncio
async def test_distill_no_force_schedules(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    # Gate the scheduler off so schedule_distill no-ops cleanly (no background task).
    monkeypatch.setenv("BR8N_LIVING_DOCS", "0")

    import br8n.store as store_pkg

    store_pkg._local_stores.clear()

    from br8n.interfaces.mcp import server

    res = await server._distill_impl("proj", "main", str(tmp_path), force=False)

    assert res["distilled"] is False
    assert res["forced"] is False
    assert res["scheduled"] is True
    assert res["project"] == "proj"
    assert res["kb"] == "main"

    store_pkg._local_stores.clear()
