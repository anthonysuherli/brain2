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
async def test_run_timeline_appends_and_regenerates(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BR8N_TIMELINE_LLM", "0")  # deterministic day-headers

    import br8n.store as store_pkg
    import br8n.livingdocs.notes as notes_mod

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.livingdocs.paths import DocPaths
    from br8n.livingdocs.state import load_timeline_state
    from br8n.livingdocs.timeline import run_timeline

    ctx = resolve_tenant("proj", "main", create=True)
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# First note\n\nDecided the cursor design.",
        session_id="s1", title="First note",
    )

    res = await run_timeline(ctx, project="proj", project_path=str(tmp_path), kb="main")
    assert res["appended"] == 1

    p = DocPaths(project_path=str(tmp_path), kb="main")
    all_time = (p.timeline_dir / "all-time.md").read_text()
    assert "# Activity — proj/main" in all_time
    assert "First note" in all_time
    assert (p.timeline_dir / "recent.md").exists()
    assert (p.timeline_dir / "week.md").exists()

    # cursor advanced + counter reset
    st = load_timeline_state(p)
    assert st.last_event_ts != ""
    assert st.events_since_pass == 0
    assert st.last_pass_at != ""

    # second pass with no new events appends nothing, doesn't rewrite all-time
    before = all_time
    res2 = await run_timeline(ctx, project="proj", project_path=str(tmp_path), kb="main")
    assert res2["appended"] == 0
    assert (p.timeline_dir / "all-time.md").read_text() == before

    store_pkg._local_stores.clear()


@pytest.mark.asyncio
async def test_run_timeline_best_effort_on_bad_store(tmp_path, monkeypatch):
    """A failure inside the pass returns {'appended': 0}, never raises."""
    import br8n.livingdocs.timeline as tl

    async def _boom(*a, **k):
        raise RuntimeError("store down")

    monkeypatch.setattr(tl, "_gather_events", _boom)
    from br8n.agent.state import TenantContext

    ctx = TenantContext(user_id="local", org_id="local", project_id="p",
                        kb_id="k", thread_id="t", access_token="")
    res = await tl.run_timeline(ctx, project="p", project_path=str(tmp_path), kb="main")
    assert res == {"appended": 0}
