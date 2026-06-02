"""Tests for the KG-schema + build MCP tools.

All six tools:
  brain2_propose_kg_schema
  brain2_set_kg_schema
  brain2_get_kg_schema
  brain2_build_graph
  brain2_graph
  brain2_kg_stats

No network / LLM calls — every external boundary is mocked.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from brain2.interfaces.mcp import server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_ctx(
    org_id: str = "org-1",
    project_id: str = "proj-1",
    kb_id: str = "kb-1",
    access_token: str = "tok",
) -> MagicMock:
    ctx = MagicMock()
    ctx.org_id = org_id
    ctx.project_id = project_id
    ctx.kb_id = kb_id
    ctx.access_token = access_token
    return ctx


_MINIMAL_VALID_SCHEMA = {
    "node_types": [{"name": "repo", "description": "A repository"}],
    "relation_types": [{"name": "contains"}],
    "relation_validity": [],
    "competency_questions": ["What repos exist?"],
}


# ---------------------------------------------------------------------------
# brain2_set_kg_schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_kg_schema_rejects_invalid():
    """A dict that does not parse as KGSchema → ok=False, errors present."""
    with patch(
        "brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()
    ):
        result = await server.brain2_set_kg_schema("proj", "kb", {"not": "a schema"})
    # Must not raise; must return error shape
    assert result["ok"] is False
    assert "errors" in result
    assert len(result["errors"]) > 0


@pytest.mark.asyncio
async def test_set_kg_schema_rejects_empty_node_types():
    """A schema with an empty node_types list fails validate_schema."""
    bad = {
        "node_types": [],
        "relation_types": [],
        "relation_validity": [],
        "competency_questions": [],
    }
    with patch(
        "brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()
    ):
        result = await server.brain2_set_kg_schema("proj", "kb", bad)
    assert result["ok"] is False
    assert "errors" in result


@pytest.mark.asyncio
async def test_set_kg_schema_accepts_valid():
    """A well-formed schema → ok=True, schema key present."""
    stored_return = {"version": 1, "schema": _MINIMAL_VALID_SCHEMA}
    mock_store = MagicMock()
    mock_store.set_kg_intent.return_value = stored_return

    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch("brain2.interfaces.mcp.server.get_store", return_value=mock_store),
    ):
        result = await server.brain2_set_kg_schema("proj", "kb", _MINIMAL_VALID_SCHEMA)

    assert result["ok"] is True
    assert "schema" in result
    mock_store.set_kg_intent.assert_called_once()


@pytest.mark.asyncio
async def test_set_kg_schema_rejects_bad_attribute_type():
    """An attribute with an unknown type fails validate_schema."""
    bad = {
        "node_types": [
            {
                "name": "thing",
                "attributes": [{"name": "x", "type": "blob"}],  # "blob" not in _ATTR_TYPES
            }
        ],
        "relation_types": [],
        "relation_validity": [],
        "competency_questions": [],
    }
    with patch(
        "brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()
    ):
        result = await server.brain2_set_kg_schema("proj", "kb", bad)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# brain2_get_kg_schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_kg_schema_returns_intent_and_emergent():
    """Returns dict with intent (from store) and emergent (from kg_stats)."""
    intent_return = {"version": 1, "schema": _MINIMAL_VALID_SCHEMA}
    stats_return = {
        "node_count": 5,
        "edge_count": 3,
        "by_type": {"repo": 2, "branch": 3},
        "by_relation": {"contains": 3},
    }
    mock_store = MagicMock()
    mock_store.get_kg_intent.return_value = intent_return
    mock_store.kg_stats.return_value = stats_return

    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch("brain2.interfaces.mcp.server.get_store", return_value=mock_store),
    ):
        result = await server.brain2_get_kg_schema("proj", "kb")

    assert "intent" in result
    assert "emergent" in result
    assert result["intent"] == intent_return
    assert result["emergent"] == stats_return


@pytest.mark.asyncio
async def test_get_kg_schema_null_intent_when_none():
    """When no intent schema is set, intent key is None."""
    mock_store = MagicMock()
    mock_store.get_kg_intent.return_value = None
    mock_store.kg_stats.return_value = {"node_count": 0, "edge_count": 0, "by_type": {}, "by_relation": {}}

    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch("brain2.interfaces.mcp.server.get_store", return_value=mock_store),
    ):
        result = await server.brain2_get_kg_schema("proj", "kb")

    assert result["intent"] is None


# ---------------------------------------------------------------------------
# brain2_propose_kg_schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_kg_schema_returns_schema_dict():
    """Returns a schema dict from propose_schema."""
    from brain2.knowledge_graph.models import KGSchema

    mock_schema = KGSchema(
        node_types=[],
        relation_types=[],
        relation_validity=[],
        competency_questions=[],
    )
    mock_store = MagicMock()
    mock_store.list_findings.return_value = {
        "findings": [{"id": "f1", "title": "T", "content": "C", "category": "cat"}]
    }
    mock_store.kg_stats.return_value = {"node_count": 0, "edge_count": 0, "by_type": {}, "by_relation": {}}

    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch("brain2.interfaces.mcp.server.get_store", return_value=mock_store),
        patch(
            "brain2.interfaces.mcp.server.propose_schema",
            new=AsyncMock(return_value=mock_schema),
        ),
    ):
        result = await server.brain2_propose_kg_schema("proj", "kb")

    # Must be a dict (model_dump output)
    assert isinstance(result, dict)
    assert "node_types" in result


@pytest.mark.asyncio
async def test_propose_kg_schema_adds_note_on_empty_kb():
    """When KB has no findings, result carries a `note` key."""
    from brain2.knowledge_graph.models import KGSchema

    mock_schema = KGSchema(
        node_types=[],
        relation_types=[],
        relation_validity=[],
        competency_questions=[],
    )
    mock_store = MagicMock()
    mock_store.list_findings.return_value = {"findings": []}
    mock_store.kg_stats.return_value = {"node_count": 0, "edge_count": 0, "by_type": {}, "by_relation": {}}

    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch("brain2.interfaces.mcp.server.get_store", return_value=mock_store),
        patch(
            "brain2.interfaces.mcp.server.propose_schema",
            new=AsyncMock(return_value=mock_schema),
        ),
    ):
        result = await server.brain2_propose_kg_schema("proj", "kb")

    assert "note" in result


# ---------------------------------------------------------------------------
# brain2_kg_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kg_stats_returns_store_output():
    """Passes through store.kg_stats unchanged."""
    expected = {"node_count": 10, "edge_count": 5, "by_type": {"repo": 10}, "by_relation": {"uses": 5}}
    mock_store = MagicMock()
    mock_store.kg_stats.return_value = expected

    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch("brain2.interfaces.mcp.server.get_store", return_value=mock_store),
    ):
        result = await server.brain2_kg_stats("proj", "kb")

    assert result == expected
    mock_store.kg_stats.assert_called_once_with("kb-1")


# ---------------------------------------------------------------------------
# brain2_graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_returns_nodes_edges_with_counts():
    """Returns nodes, edges, node_count, edge_count."""
    nodes = [{"id": "n1", "label": "brain2"}]
    edges = [{"id": "e1", "relation": "contains"}]
    mock_store = MagicMock()
    mock_store.get_kg_subgraph.return_value = {"nodes": nodes, "edges": edges}

    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch("brain2.interfaces.mcp.server.get_store", return_value=mock_store),
    ):
        result = await server.brain2_graph("proj", "kb")

    assert result["nodes"] == nodes
    assert result["edges"] == edges
    assert result["node_count"] == 1
    assert result["edge_count"] == 1


@pytest.mark.asyncio
async def test_graph_passes_focus_and_depth():
    """focus and depth are forwarded to get_kg_subgraph (as seed_node_ids + depth kwarg)."""
    mock_store = MagicMock()
    mock_store.get_kg_subgraph.return_value = {"nodes": [], "edges": []}
    # match_kg_nodes used when focus is a string
    mock_store.match_kg_nodes = AsyncMock(return_value=[{"id": "n1", "similarity": 0.9}])

    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch("brain2.interfaces.mcp.server.get_store", return_value=mock_store),
    ):
        result = await server.brain2_graph("proj", "kb", focus="brain2", depth=1)

    assert "nodes" in result
    assert "edges" in result
    mock_store.get_kg_subgraph.assert_called_once()
    call_kwargs = mock_store.get_kg_subgraph.call_args
    # depth=1 is within the config max (4) so it should be forwarded as-is.
    assert call_kwargs.kwargs.get("depth") == 1


# ---------------------------------------------------------------------------
# brain2_build_graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_graph_returns_counts():
    """Delegates to build_graph and returns its dict."""
    build_result = {
        "findings_scanned": 3,
        "nodes_created": 5,
        "edges_created": 4,
        "node_count": 5,
        "edge_count": 4,
    }
    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch(
            "brain2.interfaces.mcp.server.build_graph",
            new=AsyncMock(return_value=build_result),
        ),
    ):
        result = await server.brain2_build_graph("proj", "kb")

    assert result == build_result


@pytest.mark.asyncio
async def test_build_graph_forwards_kwargs():
    """max_findings, rebuild, use_schema are forwarded to build_graph."""
    build_result = {
        "findings_scanned": 1,
        "nodes_created": 1,
        "edges_created": 0,
        "node_count": 1,
        "edge_count": 0,
    }
    mock_build = AsyncMock(return_value=build_result)

    with (
        patch("brain2.interfaces.mcp.server.resolve_tenant", return_value=_mock_ctx()),
        patch("brain2.interfaces.mcp.server.build_graph", new=mock_build),
    ):
        await server.brain2_build_graph("proj", "kb", max_findings=10, rebuild=False, use_schema=False)

    mock_build.assert_called_once()
    call_kwargs = mock_build.call_args.kwargs
    assert call_kwargs.get("max_findings") == 10
    assert call_kwargs.get("rebuild") is False
    assert call_kwargs.get("use_schema") is False
