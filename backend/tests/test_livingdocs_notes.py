"""Local-tier test for persist_note: a note lands as BOTH a `note` Finding
and a markdown file under .br8n/notes/<kb>/.

Mirrors test_engine_local.py: BR8N_BACKEND=local + a tmp BR8N_DB_PATH wire
the real SQLiteStore (no storage mocks); only the embedder is faked so no OpenAI
call is made, and the synopsis rebuild is patched so the post-write hook is a
no-op (no Anthropic).
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
async def test_persist_note_writes_finding_and_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))

    import br8n.livingdocs.notes as notes_mod
    import br8n.store as store_pkg

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    # Keep the synopsis rebuild a no-op (avoid Anthropic on the post-write hook).
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.livingdocs.paths import DocPaths
    from br8n.store import get_store

    ctx = resolve_tenant("proj", "main", create=True)
    note_md = "# Session\n\n## Decisions\nChose X over Y."
    res = await persist_note(
        ctx,
        project_path=str(tmp_path),
        kb="main",
        content=note_md,
        session_id="sess-123",
        title="Chose X over Y",
    )

    store = get_store(ctx.access_token, org_id=ctx.org_id)
    listed = store.list_findings(ctx.kb_id, category="note")
    assert listed["count"] == 1

    p = DocPaths(project_path=str(tmp_path), kb="main")
    files = list(p.notes_dir.glob("*.md"))
    assert len(files) == 1
    assert "Chose X over Y" in files[0].read_text()

    assert res["finding_id"]
    assert res["note_path"].endswith(".md")

    store_pkg._local_stores.clear()
