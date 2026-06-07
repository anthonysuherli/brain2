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
async def test_timeline_tool_force_builds(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BR8N_TIMELINE_LLM", "0")

    import br8n.store as store_pkg
    import br8n.livingdocs.notes as notes_mod

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.interfaces.mcp.server import _timeline_impl

    ctx = resolve_tenant("proj", "main", create=True)
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# n\n\nbody", session_id="s1", title="n",
    )
    res = await _timeline_impl("proj", "main", str(tmp_path), force=True)
    assert res["forced"] is True
    assert res["appended"] == 1
    assert res["project"] == "proj"

    store_pkg._local_stores.clear()


@pytest.mark.asyncio
async def test_timeline_tool_no_force_schedules(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))

    import br8n.store as store_pkg
    store_pkg._local_stores.clear()

    from br8n.interfaces.mcp.server import _timeline_impl

    res = await _timeline_impl("proj", "main", str(tmp_path), force=False)
    assert res["forced"] is False
    assert res["scheduled"] is True

    store_pkg._local_stores.clear()
