"""Local-tier test for persist_journal: a `journal` Finding + a global markdown
file, with NO synopsis rebuild. Mirrors test_note_tool.py's harness — real
SQLiteStore via tmp BRAIN2_DB_PATH, only the embedder faked.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DIM = 1536


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


async def test_persist_journal_writes_finding_and_global_md(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))

    import brain2.livingdocs.journal as journal_mod
    import brain2.store as store_pkg
    from brain2.constants import JOURNAL_SCOPE
    from brain2.interfaces.mcp.tenancy import resolve_tenant

    store_pkg._local_stores.clear()
    monkeypatch.setattr(journal_mod, "embed_batch", _fake_embed_batch)

    ctx = resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=True)
    res = await journal_mod.persist_journal(
        ctx, text="learned that X composes cleanly", type="insight", tags=["arch"]
    )

    assert res["finding_id"]
    assert res["entry_path"].endswith(".md")
    # markdown mirror lives in the GLOBAL journal dir (tmp BRAIN2_DB_PATH parent)
    assert Path(res["entry_path"]).parent == tmp_path / "journal"
    assert Path(res["entry_path"]).exists()

    store = store_pkg.get_store(ctx.access_token)
    got = store.get_finding(ctx.kb_id, res["finding_id"])
    assert got["category"] == "journal"
    assert "journal" in got["tags"] and "insight" in got["tags"] and "arch" in got["tags"]

    store_pkg._local_stores.clear()
