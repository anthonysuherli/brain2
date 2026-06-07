import asyncio

import pytest


def test_schedule_timeline_gated_off_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_TIMELINE", "0")
    from br8n.agent.state import TenantContext
    from br8n.livingdocs.paths import DocPaths
    from br8n.livingdocs.state import load_timeline_state
    from br8n.livingdocs.timeline import schedule_timeline

    ctx = TenantContext(user_id="local", org_id="local", project_id="p",
                        kb_id="k", thread_id="t", access_token="")
    schedule_timeline(ctx, project="p", project_path=str(tmp_path), kb="main")
    # counter not bumped, no state file written
    st = load_timeline_state(DocPaths(project_path=str(tmp_path), kb="main"))
    assert st.events_since_pass == 0


@pytest.mark.asyncio
async def test_schedule_timeline_bumps_and_fires(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_TIMELINE", "1")
    monkeypatch.setenv("BR8N_LIVING_DOCS", "1")

    import br8n.livingdocs.timeline as tl

    fired = {"n": 0}

    async def _fake_run(ctx, *, project, project_path, kb):
        fired["n"] += 1
        return {"appended": 0}

    monkeypatch.setattr(tl, "run_timeline", _fake_run)
    # debounce_n=1 → first event trips immediately
    monkeypatch.setattr(
        tl, "get_config",
        lambda: type("C", (), {"living_docs": type("L", (), {
            "timeline_debounce_n": 1, "timeline_debounce_minutes": 60})()})(),
    )

    from br8n.agent.state import TenantContext

    ctx = TenantContext(user_id="local", org_id="local", project_id="p",
                        kb_id="k", thread_id="t", access_token="")
    tl.schedule_timeline(ctx, project="p", project_path=str(tmp_path), kb="main")
    await asyncio.sleep(0)  # let the created task run
    # drain any scheduled tasks
    for t in list(tl._BG_TASKS):
        await t
    assert fired["n"] == 1
