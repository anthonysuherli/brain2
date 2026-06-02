"""SQLiteStore activity-graph methods against a real in-memory SQLite + sqlite-vec.

Node embeddings are small real vectors and ``match_kg_nodes`` runs the actual
``vec_distance_cosine`` KNN — no mocks of the vector search.
"""

from __future__ import annotations

import pytest

from brain2.store import SQLiteStore, SupabaseStore
from brain2.store.sqlite import _ORG

DIM = 1536


def _vec(seed: list[float]) -> list[float]:
    v = list(seed) + [0.0] * (DIM - len(seed))
    return v[:DIM]


@pytest.fixture
def store() -> SQLiteStore:
    return SQLiteStore(":memory:")


def _node(type: str, label: str, *, embedding=None, **kw) -> dict:
    return {
        "org_id": "ignored",
        "type": type,
        "label": label,
        "properties": kw.get("properties", {}),
        "grounded_in": kw.get("grounded_in", []),
        "embedding": embedding,
    }


# --- node upsert + dedupe + merge -------------------------------------------


async def test_upsert_nodes_returns_ids_in_order(store):
    ids = await store.upsert_kg_nodes(
        "akb",
        [_node("repo", "brain2"), _node("branch", "dev"), _node("file", "store/base.py")],
    )
    assert len(ids) == 3
    assert len(set(ids)) == 3


async def test_upsert_dedupes_within_batch_by_type_and_label(store):
    ids = await store.upsert_kg_nodes(
        "akb",
        [_node("file", "a.py"), _node("file", "a.py"), _node("file", "b.py")],
    )
    # The two "file/a.py" collapse to one id; "b.py" is distinct.
    assert ids[0] == ids[1] != ids[2]


async def test_same_label_different_type_are_distinct(store):
    ids = await store.upsert_kg_nodes("akb", [_node("repo", "main"), _node("branch", "main")])
    assert ids[0] != ids[1]


async def test_upsert_reuses_existing_node_and_merges(store):
    [first] = await store.upsert_kg_nodes(
        "akb", [_node("repo", "brain2", properties={"path": "/a"}, grounded_in=["f1"])]
    )
    [second] = await store.upsert_kg_nodes(
        "akb", [_node("repo", "brain2", properties={"path": "/b", "extra": 1}, grounded_in=["f2"])]
    )
    assert second == first  # same node reused
    # Existing properties win on conflict; new keys added; grounding unions.
    row = store._conn.execute(
        "SELECT properties, grounded_in FROM kg_nodes WHERE id = ?;", (first,)
    ).fetchone()
    import json

    props = json.loads(row["properties"])
    grounded = json.loads(row["grounded_in"])
    assert props["path"] == "/a"  # existing wins
    assert props["extra"] == 1  # new key merged
    assert grounded == ["f1", "f2"]


async def test_upsert_scopes_dedupe_to_kb(store):
    [a] = await store.upsert_kg_nodes("kb1", [_node("repo", "brain2")])
    [b] = await store.upsert_kg_nodes("kb2", [_node("repo", "brain2")])
    assert a != b  # same label in different KBs → different nodes


async def test_upsert_forces_local_org(store):
    [nid] = await store.upsert_kg_nodes("akb", [_node("repo", "brain2")])
    org = store._conn.execute("SELECT org_id FROM kg_nodes WHERE id = ?;", (nid,)).fetchone()["org_id"]
    assert org == _ORG


# --- edge upsert + dedupe ---------------------------------------------------


async def test_upsert_edges_dedupes_and_drops_self_loops(store):
    a, b = await store.upsert_kg_nodes("akb", [_node("session", "s1"), _node("repo", "brain2")])
    n = await store.upsert_kg_edges(
        "akb",
        [
            {"source_node_id": a, "target_node_id": b, "relation": "on_repo"},
            {"source_node_id": a, "target_node_id": b, "relation": "on_repo"},  # dupe
            {"source_node_id": a, "target_node_id": a, "relation": "on_repo"},  # self-loop
            {"source_node_id": a, "target_node_id": None, "relation": "x"},  # dangling
        ],
    )
    assert n == 1
    # Re-inserting the same edge in a later call is also skipped (idempotent re-capture).
    again = await store.upsert_kg_edges(
        "akb", [{"source_node_id": a, "target_node_id": b, "relation": "on_repo"}]
    )
    assert again == 0


# --- match_kg_nodes (real vector search) ------------------------------------


async def test_match_kg_nodes_ranking(store):
    await store.upsert_kg_nodes(
        "akb",
        [
            _node("task", "A", embedding=_vec([1.0, 0.0, 0.0])),
            _node("task", "B", embedding=_vec([0.0, 1.0, 0.0])),
        ],
    )
    out = await store.match_kg_nodes("akb", _vec([0.9, 0.1, 0.0]), match_count=10, min_similarity=0.0)
    assert out[0]["label"] == "A"
    assert all("similarity" in r for r in out)


# --- subgraph ---------------------------------------------------------------


async def test_subgraph_seeded_pulls_neighbours(store):
    s, r, f = await store.upsert_kg_nodes(
        "akb", [_node("session", "s1"), _node("repo", "brain2"), _node("file", "x.py")]
    )
    await store.upsert_kg_edges(
        "akb",
        [
            {"source_node_id": s, "target_node_id": r, "relation": "on_repo"},
            {"source_node_id": s, "target_node_id": f, "relation": "edited"},
        ],
    )
    sub = store.get_kg_subgraph("akb", seed_node_ids=[s])
    assert {n["id"] for n in sub["nodes"]} == {s, r, f}
    assert len(sub["edges"]) == 2


async def test_subgraph_full_when_no_seed(store):
    await store.upsert_kg_nodes("akb", [_node("repo", "brain2"), _node("branch", "dev")])
    sub = store.get_kg_subgraph("akb")
    assert len(sub["nodes"]) == 2


# --- list + stats -----------------------------------------------------------


async def test_list_kg_nodes_type_filter_and_recency(store):
    await store.upsert_kg_nodes(
        "akb", [_node("session", "s1"), _node("repo", "brain2"), _node("session", "s2")]
    )
    sessions = store.list_kg_nodes("akb", type="session")
    assert {n["label"] for n in sessions} == {"s1", "s2"}
    assert all(n["type"] == "session" for n in sessions)


async def test_kg_stats_breakdowns(store):
    s, r = await store.upsert_kg_nodes("akb", [_node("session", "s1"), _node("repo", "brain2")])
    await store.upsert_kg_edges(
        "akb", [{"source_node_id": s, "target_node_id": r, "relation": "on_repo"}]
    )
    stats = store.kg_stats("akb")
    assert stats["node_count"] == 2
    assert stats["edge_count"] == 1
    assert stats["by_type"] == {"session": 1, "repo": 1}
    assert stats["by_relation"] == {"on_repo": 1}


# --- interchangeability with SupabaseStore ----------------------------------


def test_graph_protocol_parity_with_supabase():
    for m in (
        "upsert_kg_nodes", "upsert_kg_edges", "match_kg_nodes",
        "get_kg_subgraph", "list_kg_nodes", "get_kg_node", "kg_stats",
    ):
        assert hasattr(SQLiteStore, m) and hasattr(SupabaseStore, m)


# --- update_kg_node (overwrite, not merge) ----------------------------------


async def test_update_kg_node_overwrites_properties(store):
    [nid] = await store.upsert_kg_nodes(
        "akb", [_node("concept", "x compounds", properties={"body": "old", "version": 1})]
    )
    await store.update_kg_node(
        "akb", nid, properties={"body": "new", "version": 2}
    )
    rows = store.list_kg_nodes("akb", type="concept")
    props = next(r for r in rows if r["id"] == nid)["properties"]
    assert props["body"] == "new"
    assert props["version"] == 2


async def test_update_kg_node_replaces_grounded_and_reembeds(store):
    [nid] = await store.upsert_kg_nodes(
        "akb",
        [_node("concept", "y", embedding=_vec([1.0, 0.0]), grounded_in=["f1"])],
    )
    await store.update_kg_node(
        "akb", nid, properties={"body": "b"},
        grounded_in=["f1", "f2"], embedding=_vec([0.0, 1.0]),
    )
    rows = store.list_kg_nodes("akb", type="concept")
    assert next(r for r in rows if r["id"] == nid)["grounded_in"] == ["f1", "f2"]
    hits = await store.match_kg_nodes("akb", _vec([0.0, 1.0]), match_count=1, min_similarity=0.5)
    assert hits and hits[0]["id"] == nid


# --- get_kg_node (by-id, full row) ------------------------------------------


async def test_get_kg_node_returns_full_decoded_row(store):
    [nid] = await store.upsert_kg_nodes(
        "akb",
        [_node("concept", "x compounds",
               properties={"body": "deep", "version": 3},
               grounded_in=["f1", "f2"])],
    )
    node = store.get_kg_node("akb", nid)
    assert node is not None
    assert node["id"] == nid
    assert node["type"] == "concept"
    assert node["label"] == "x compounds"
    assert node["properties"] == {"body": "deep", "version": 3}
    assert node["grounded_in"] == ["f1", "f2"]


async def test_get_kg_node_unknown_id_returns_none(store):
    await store.upsert_kg_nodes("akb", [_node("concept", "x")])
    assert store.get_kg_node("akb", "does-not-exist") is None
