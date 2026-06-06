"""Wiring test for br8n.agent.resume.resume_preamble — mocked, no store/embeddings."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def test_resume_preamble_wires_resolve_store_and_select():
    from br8n.agent.resume import ResumeResult, resume_preamble

    fake_ctx = MagicMock(access_token="tok", org_id="org1", kb_id="kb1")
    fake_store = MagicMock()

    with (
        patch("br8n.interfaces.mcp.tenancy.resolve_tenant", return_value=fake_ctx) as m_rt,
        patch("br8n.store.get_store", return_value=fake_store) as m_gs,
        patch(
            "br8n.agent.resume.select_preamble",
            new=AsyncMock(return_value=("<preamble/>", "rich")),
        ) as m_sp,
    ):
        res = await resume_preamble("proj", "dev", "my query", depth="deep")

    assert isinstance(res, ResumeResult)
    assert res.preamble == "<preamble/>"
    assert res.coverage == "rich"
    assert res.ctx is fake_ctx
    assert res.store is fake_store
    m_rt.assert_called_once_with("proj", "dev", create=False, principal=None)
    m_gs.assert_called_once_with("tok", org_id="org1")
    m_sp.assert_awaited_once_with("my query", store=fake_store, kb_id="kb1", depth="deep")


async def test_resume_preamble_propagates_not_found():
    from br8n.agent.resume import resume_preamble

    with patch(
        "br8n.interfaces.mcp.tenancy.resolve_tenant",
        side_effect=RuntimeError("kb dev not found"),
    ):
        with pytest.raises(RuntimeError, match="not found"):
            await resume_preamble("proj", "dev", "q")
