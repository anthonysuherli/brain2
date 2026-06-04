"""Local-tier test for brain2_journal_search scope filters. Seeds findings
directly (journal entry in the __journal__ KB, a note in a project KB) and
asserts each scope returns the right corpus. embed_text is faked at its source
module so the search path makes no OpenAI call.
"""
from __future__ import annotations

import hashlib

DIM = 1536


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_text(text: str) -> list[float]:
    return _fake_vec(text)


async def test_journal_search_scopes(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setattr("brain2.clients.embeddings.embed_text", _fake_embed_text)

    import brain2.store as store_pkg
    from brain2.constants import JOURNAL_SCOPE
    from brain2.interfaces.mcp import server
    from brain2.interfaces.mcp.tenancy import resolve_tenant

    store_pkg._local_stores.clear()
    jctx = resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=True)
    pctx = resolve_tenant("proj", "main", create=True)
    store = store_pkg.get_store()
    await store.insert_findings(
        [
            {"kb_id": jctx.kb_id, "title": "j-entry", "content": "alpha insight",
             "category": "journal", "tags": ["journal", "insight"],
             "embedding": _fake_vec("alpha insight")},
            {"kb_id": pctx.kb_id, "title": "p-note", "content": "beta note",
             "category": "note", "tags": ["note"],
             "embedding": _fake_vec("beta note")},
        ]
    )

    j = await server._journal_search_impl("alpha", scope="journal")
    assert {r["title"] for r in j["results"]} == {"j-entry"}

    p = await server._journal_search_impl("beta", scope="project", project="proj", kb="main")
    assert {r["title"] for r in p["results"]} == {"p-note"}

    b = await server._journal_search_impl("alpha", scope="both")
    assert {r["title"] for r in b["results"]} == {"j-entry", "p-note"}

    # type filter narrows journal results
    none = await server._journal_search_impl("alpha", scope="journal", type="reflection")
    assert none["results"] == []

    store_pkg._local_stores.clear()
