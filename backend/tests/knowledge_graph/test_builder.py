"""Unit tests for br8n.knowledge_graph.builder (stubbed extractor, no LLM calls)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from br8n.knowledge_graph import builder
from br8n.knowledge_graph.models import KGEdge, KGExtraction, KGNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(kb_id: str = "kb1", org_id: str = "org1") -> MagicMock:
    ctx = MagicMock()
    ctx.kb_id = kb_id
    ctx.org_id = org_id
    ctx.access_token = ""
    return ctx


def _fake_store(findings=None, kg_intent=None) -> MagicMock:
    store = MagicMock()
    findings_list = findings or []
    store.list_findings.return_value = {"count": len(findings_list), "findings": findings_list}
    store.get_kg_intent.return_value = kg_intent
    store.upsert_kg_nodes = AsyncMock(return_value=[f"node-id-{i}" for i in range(20)])
    store.upsert_kg_edges = AsyncMock(return_value=0)
    store.clear_kg = MagicMock()
    store.kg_stats.return_value = {"node_count": 1, "edge_count": 0}
    return store


# ---------------------------------------------------------------------------
# Test: basic extract-and-persist flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_graph_calls_extract_and_persists(tmp_path):
    """The builder extracts nodes from findings and persists them via the store."""
    fake_findings = [{"id": "f1", "title": "FastMCP", "content": {}, "category": "tool"}]
    fake_extraction = KGExtraction(
        nodes=[KGNode(label="FastMCP", type="library", grounded_in=["f1"])],
        edges=[],
    )
    fake_ctx = _make_ctx()
    fake_store = _fake_store(findings=fake_findings)

    with (
        patch("br8n.knowledge_graph.builder.extract_graph", new=AsyncMock(return_value=fake_extraction)),
        patch("br8n.knowledge_graph.builder.get_store", return_value=fake_store),
        patch("br8n.knowledge_graph.builder.embed_batch", new=AsyncMock(return_value=[[0.1] * 3])),
    ):
        result = await builder.build_graph(fake_ctx, rebuild=True, use_schema=False)

    assert result["nodes_created"] >= 1
    fake_store.upsert_kg_nodes.assert_called_once()
    # Edges: none in this extraction, so upsert_kg_edges should not be called.
    fake_store.upsert_kg_edges.assert_not_called()


# ---------------------------------------------------------------------------
# Test: rebuild=True clears the graph before inserting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_graph_rebuild_clears_existing_nodes():
    """rebuild=True must call store.clear_kg before upserting new nodes."""
    fake_findings = [{"id": "f1", "title": "SomeTool", "content": {}, "category": "tool"}]
    fake_extraction = KGExtraction(
        nodes=[KGNode(label="SomeTool", type="tool", grounded_in=["f1"])],
        edges=[],
    )
    fake_ctx = _make_ctx()
    fake_store = _fake_store(findings=fake_findings)

    with (
        patch("br8n.knowledge_graph.builder.extract_graph", new=AsyncMock(return_value=fake_extraction)),
        patch("br8n.knowledge_graph.builder.get_store", return_value=fake_store),
        patch("br8n.knowledge_graph.builder.embed_batch", new=AsyncMock(return_value=[[0.1] * 3])),
    ):
        await builder.build_graph(fake_ctx, rebuild=True, use_schema=False)

    fake_store.clear_kg.assert_called_once_with("kb1")


@pytest.mark.asyncio
async def test_build_graph_no_rebuild_skips_clear():
    """rebuild=False must NOT call store.clear_kg."""
    fake_findings = [{"id": "f1", "title": "SomeTool", "content": {}, "category": "tool"}]
    fake_extraction = KGExtraction(
        nodes=[KGNode(label="SomeTool", type="tool", grounded_in=["f1"])],
        edges=[],
    )
    fake_ctx = _make_ctx()
    fake_store = _fake_store(findings=fake_findings)

    with (
        patch("br8n.knowledge_graph.builder.extract_graph", new=AsyncMock(return_value=fake_extraction)),
        patch("br8n.knowledge_graph.builder.get_store", return_value=fake_store),
        patch("br8n.knowledge_graph.builder.embed_batch", new=AsyncMock(return_value=[[0.1] * 3])),
    ):
        await builder.build_graph(fake_ctx, rebuild=False, use_schema=False)

    fake_store.clear_kg.assert_not_called()


# ---------------------------------------------------------------------------
# Test: empty findings → early return, no LLM call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_graph_empty_findings_returns_zeros():
    """When there are no findings, build_graph returns all-zero counts."""
    fake_ctx = _make_ctx()
    fake_store = _fake_store(findings=[])

    with (
        patch("br8n.knowledge_graph.builder.extract_graph", new=AsyncMock()) as mock_extract,
        patch("br8n.knowledge_graph.builder.get_store", return_value=fake_store),
    ):
        result = await builder.build_graph(fake_ctx, rebuild=True, use_schema=False)

    assert result == {
        "findings_scanned": 0,
        "nodes_created": 0,
        "edges_created": 0,
        "node_count": 0,
        "edge_count": 0,
    }
    mock_extract.assert_not_called()


# ---------------------------------------------------------------------------
# Test: incremental build raises NotImplementedError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_graph_incremental_raises():
    """Passing finding_ids (incremental build) raises NotImplementedError in v1."""
    fake_ctx = _make_ctx()
    with pytest.raises(NotImplementedError):
        await builder.build_graph(fake_ctx, finding_ids=["f1", "f2"])


# ---------------------------------------------------------------------------
# Test: schema loaded from store when use_schema=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_graph_loads_schema_when_use_schema_true():
    """When use_schema=True and a schema exists, the builder passes it to extract_graph."""
    fake_findings = [{"id": "f1", "title": "SomeTool", "content": {}, "category": "tool"}]
    fake_intent = {
        "version": 1,
        "schema": {
            "node_types": [{"name": "tool", "description": "a dev tool", "examples": [],
                            "attributes": [], "layer": ""}],
            "relation_types": [],
            "relation_validity": [],
            "competency_questions": [],
            "regime": "soft",
        },
    }
    fake_extraction = KGExtraction(
        nodes=[KGNode(label="SomeTool", type="tool", grounded_in=["f1"])],
        edges=[],
    )
    fake_ctx = _make_ctx()
    fake_store = _fake_store(findings=fake_findings, kg_intent=fake_intent)

    with (
        patch("br8n.knowledge_graph.builder.extract_graph", new=AsyncMock(return_value=fake_extraction)) as mock_extract,
        patch("br8n.knowledge_graph.builder.get_store", return_value=fake_store),
        patch("br8n.knowledge_graph.builder.embed_batch", new=AsyncMock(return_value=[[0.1] * 3])),
    ):
        await builder.build_graph(fake_ctx, rebuild=False, use_schema=True)

    # extract_graph is called as extract_graph(findings, cfg, schema) — positionally.
    args, _ = mock_extract.call_args
    # schema is the 3rd positional argument (index 2).
    assert len(args) >= 3 and args[2] is not None


@pytest.mark.asyncio
async def test_build_graph_no_schema_when_use_schema_false():
    """When use_schema=False, extract_graph receives schema=None."""
    fake_findings = [{"id": "f1", "title": "SomeTool", "content": {}, "category": "tool"}]
    fake_extraction = KGExtraction(
        nodes=[KGNode(label="SomeTool", type="tool", grounded_in=["f1"])],
        edges=[],
    )
    fake_ctx = _make_ctx()
    fake_store = _fake_store(findings=fake_findings)

    with (
        patch("br8n.knowledge_graph.builder.extract_graph", new=AsyncMock(return_value=fake_extraction)) as mock_extract,
        patch("br8n.knowledge_graph.builder.get_store", return_value=fake_store),
        patch("br8n.knowledge_graph.builder.embed_batch", new=AsyncMock(return_value=[[0.1] * 3])),
    ):
        await builder.build_graph(fake_ctx, rebuild=False, use_schema=False)

    args, _ = mock_extract.call_args
    # schema is the 3rd positional argument (index 2) — should be None.
    assert len(args) >= 3 and args[2] is None


# ---------------------------------------------------------------------------
# Test: edges are resolved and persisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_graph_persists_edges():
    """When extraction includes edges, upsert_kg_edges is called with the resolved rows."""
    fake_findings = [
        {"id": "f1", "title": "Alpha", "content": {}, "category": "tool"},
        {"id": "f2", "title": "Beta", "content": {}, "category": "tool"},
    ]
    fake_extraction = KGExtraction(
        nodes=[
            KGNode(label="Alpha", type="tool", grounded_in=["f1"]),
            KGNode(label="Beta", type="tool", grounded_in=["f2"]),
        ],
        edges=[
            KGEdge(source=0, target=1, relation="depends_on", grounded_in=["f1"]),
        ],
    )
    fake_ctx = _make_ctx()
    fake_store = _fake_store(findings=fake_findings)
    # Simulate two distinct node IDs being returned.
    fake_store.upsert_kg_nodes = AsyncMock(return_value=["node-alpha", "node-beta"])
    fake_store.upsert_kg_edges = AsyncMock(return_value=1)
    fake_store.kg_stats.return_value = {"node_count": 2, "edge_count": 1}

    with (
        patch("br8n.knowledge_graph.builder.extract_graph", new=AsyncMock(return_value=fake_extraction)),
        patch("br8n.knowledge_graph.builder.get_store", return_value=fake_store),
        patch("br8n.knowledge_graph.builder.embed_batch", new=AsyncMock(return_value=[[0.1] * 3, [0.2] * 3])),
    ):
        result = await builder.build_graph(fake_ctx, rebuild=True, use_schema=False)

    assert result["edges_created"] == 1
    fake_store.upsert_kg_edges.assert_called_once()
    edge_rows = fake_store.upsert_kg_edges.call_args[0][1]  # positional: (kb_id, edges)
    assert len(edge_rows) == 1
    assert edge_rows[0]["source_node_id"] == "node-alpha"
    assert edge_rows[0]["target_node_id"] == "node-beta"
    assert edge_rows[0]["relation"] == "depends_on"


# ---------------------------------------------------------------------------
# Test: _collapse_nodes dedupes on normalized label
# ---------------------------------------------------------------------------


def test_collapse_nodes_merges_duplicates():
    """Nodes with the same normalized label are merged into one."""
    nodes = [
        KGNode(label="FastMCP", type="library", grounded_in=["f1"]),
        KGNode(label="fastmcp", type="library", grounded_in=["f2"]),  # same norm
    ]
    result = builder._collapse_nodes(nodes)
    assert len(result) == 1
    # Both groundings should be present.
    assert "f1" in result[0].grounded_in
    assert "f2" in result[0].grounded_in


def test_collapse_nodes_preserves_distinct_labels():
    """Nodes with different labels pass through unchanged."""
    nodes = [
        KGNode(label="Alpha", type="tool", grounded_in=["f1"]),
        KGNode(label="Beta", type="tool", grounded_in=["f2"]),
    ]
    result = builder._collapse_nodes(nodes)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Test: _load_intent reads schema from row["schema"]
# ---------------------------------------------------------------------------


def test_load_intent_reads_schema_field():
    """_load_intent must read row['schema'], not the top-level row dict."""
    store = MagicMock()
    store.get_kg_intent.return_value = {
        "version": 1,
        "schema": {
            "node_types": [{"name": "tool", "description": "", "examples": [],
                            "attributes": [], "layer": ""}],
            "relation_types": [],
            "relation_validity": [],
            "competency_questions": [],
            "regime": "soft",
        },
    }
    schema = builder._load_intent(store, "kb1")
    assert schema is not None
    assert schema.node_types[0].name == "tool"


def test_load_intent_returns_none_when_no_schema():
    """_load_intent returns None when no schema is stored."""
    store = MagicMock()
    store.get_kg_intent.return_value = None
    schema = builder._load_intent(store, "kb1")
    assert schema is None


def test_load_intent_returns_none_on_malformed_schema(caplog):
    """_load_intent returns None (not raises) when the stored schema is malformed."""
    import logging

    store = MagicMock()
    store.get_kg_intent.return_value = {"version": 1, "schema": {"node_types": "not-a-list"}}
    with caplog.at_level(logging.WARNING, logger="br8n.knowledge_graph.builder"):
        schema = builder._load_intent(store, "kb1")
    assert schema is None
