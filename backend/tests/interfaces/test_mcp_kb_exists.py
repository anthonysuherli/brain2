"""Tests for brain2_kb_exists MCP tool — first-run guard.

The tool must:
  * Return {exists: True, ...} when resolve_tenant succeeds.
  * Return {exists: False, ...} when resolve_tenant raises RuntimeError("... not found").
  * Re-raise on any other RuntimeError (fail-closed on genuine backend errors).
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from brain2.interfaces.mcp import server


@pytest.mark.asyncio
async def test_kb_exists_true_when_tenant_resolves():
    with patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=MagicMock()):
        result = await server.brain2_kb_exists("my-project", "my-kb")
    assert result == {"exists": True, "project": "my-project", "kb": "my-kb"}


@pytest.mark.asyncio
async def test_kb_exists_false_when_not_found():
    with patch(
        "brain2.interfaces.mcp.server.resolve_tenant",
        side_effect=RuntimeError("kb my-kb not found"),
    ):
        result = await server.brain2_kb_exists("my-project", "my-kb")
    assert result == {"exists": False, "project": "my-project", "kb": "my-kb"}


@pytest.mark.asyncio
async def test_kb_exists_reraises_non_notfound_errors():
    with patch(
        "brain2.interfaces.mcp.server.resolve_tenant",
        side_effect=RuntimeError("connection refused"),
    ):
        with pytest.raises(RuntimeError, match="connection refused"):
            await server.brain2_kb_exists("my-project", "my-kb")
