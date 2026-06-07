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
async def test_gather_events_collects_notes_captures_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))

    import br8n.store as store_pkg
    import br8n.livingdocs.notes as notes_mod
    import br8n.livingdocs.journal as journal_mod

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)
    monkeypatch.setattr(journal_mod, "embed_batch", _fake_embed_batch)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.livingdocs.journal import persist_journal
    from br8n.livingdocs.timeline import _gather_events
    from br8n.capture.models import WorkspaceSnapshot
    from br8n.capture.service import persist_snapshot

    ctx = resolve_tenant("proj", "main", create=True)
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# Note one\n\nDecided on the cursor design.",
        session_id="s1", title="Note one",
    )
    snap = WorkspaceSnapshot(
        project_path=str(tmp_path), trigger="manual",
        captured_at="2026-06-07T12:00:00+00:00", branch="main",
        git_diff_stat="1 file changed", open_files=[],
        hypothesis="Wiring the timeline",
    )
    await persist_snapshot(ctx, snap)

    jctx = resolve_tenant("__journal__", "__journal__", create=True)
    await persist_journal(
        jctx, text="A thought about timelines.", type="insight",
        originating_project="proj",
    )
    await persist_journal(
        jctx, text="Unrelated project note.", type="insight",
        originating_project="other-proj",
    )

    events = await _gather_events(ctx, project="proj", since=None)
    kinds = sorted({e.kind for e in events})
    assert kinds == ["capture", "journal", "note"]
    titles = [e.title for e in events]
    assert "Note one" in titles
    # journal filtered to this project only
    journal_titles = [e.title for e in events if e.kind == "journal"]
    assert any("thought about timelines" in t.lower() for t in journal_titles)
    assert not any("unrelated" in t.lower() for t in journal_titles)

    store_pkg._local_stores.clear()


@pytest.mark.asyncio
async def test_gather_events_respects_cursor(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))

    import br8n.store as store_pkg
    import br8n.livingdocs.notes as notes_mod

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.livingdocs.timeline import _gather_events

    ctx = resolve_tenant("proj", "main", create=True)
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# Old\n\nold body", session_id="s1", title="Old",
    )
    all_events = await _gather_events(ctx, project="proj", since=None)
    assert all_events
    newest = max((e.ts, e.id) for e in all_events)
    # cursor at the newest event → nothing newer
    fresh = await _gather_events(ctx, project="proj", since=newest)
    assert fresh == []

    store_pkg._local_stores.clear()
