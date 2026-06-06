"""Tests for br8n_kb_exists MCP tool — first-run guard.

The tool must:
  * Return {exists: True, init_offered: bool, ...} when resolve_tenant succeeds.
  * Return {exists: False, init_offered: False, ...} when resolve_tenant raises
    RuntimeError("... not found").
  * Re-raise on any other RuntimeError (fail-closed on genuine backend errors).
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from br8n.interfaces.mcp import server


@pytest.mark.asyncio
async def test_kb_exists_true_when_tenant_resolves():
    mock_store = MagicMock()
    mock_store.get_init_offered.return_value = False
    with (
        patch("br8n.interfaces.mcp.server.resolve_tenant", return_value=MagicMock()),
        patch("br8n.interfaces.mcp.server.get_store", return_value=mock_store),
    ):
        result = await server.br8n_kb_exists("my-project", "my-kb")
    assert result == {
        "exists": True,
        "init_offered": False,
        "project": "my-project",
        "kb": "my-kb",
    }


@pytest.mark.asyncio
async def test_kb_exists_true_includes_init_offered_true():
    """init_offered=True when the stamp is set."""
    mock_store = MagicMock()
    mock_store.get_init_offered.return_value = True
    with (
        patch("br8n.interfaces.mcp.server.resolve_tenant", return_value=MagicMock()),
        patch("br8n.interfaces.mcp.server.get_store", return_value=mock_store),
    ):
        result = await server.br8n_kb_exists("my-project", "my-kb")
    assert result["exists"] is True
    assert result["init_offered"] is True


@pytest.mark.asyncio
async def test_kb_exists_false_when_not_found():
    with patch(
        "br8n.interfaces.mcp.server.resolve_tenant",
        side_effect=RuntimeError("kb my-kb not found"),
    ):
        result = await server.br8n_kb_exists("my-project", "my-kb")
    assert result == {
        "exists": False,
        "init_offered": False,
        "project": "my-project",
        "kb": "my-kb",
    }


@pytest.mark.asyncio
async def test_kb_exists_reraises_non_notfound_errors():
    with patch(
        "br8n.interfaces.mcp.server.resolve_tenant",
        side_effect=RuntimeError("connection refused"),
    ):
        with pytest.raises(RuntimeError, match="connection refused"):
            await server.br8n_kb_exists("my-project", "my-kb")
