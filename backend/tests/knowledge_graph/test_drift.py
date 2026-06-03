"""Unit tests for the schema-drift detector (pure over a fake store)."""

from brain2.config import get_config
from brain2.knowledge_graph.drift import assess_drift, residual_breakdown
from brain2.knowledge_graph.models import KGSchema, NodeType


def _cfg():
    return get_config().drift


class _FakeStore:
    """Minimal Store stand-in: only the two reads ``assess_drift`` touches."""

    def __init__(self, *, by_type: dict[str, int], intent: dict | None = None):
        self._by_type = by_type
        self._intent = intent

    def kg_stats(self, kb_id: str) -> dict:
        return {
            "node_count": sum(self._by_type.values()),
            "edge_count": 0,
            "by_type": dict(self._by_type),
            "by_relation": {},
        }

    def get_kg_intent(self, kb_id: str) -> dict | None:
        return self._intent


def _schema(*names: str) -> dict:
    return {"version": 1, "schema": KGSchema(node_types=[NodeType(name=n) for n in names]).model_dump()}


# --- residual_breakdown ------------------------------------------------------

def test_residual_breakdown_no_schema_counts_only_other():
    total, res = residual_breakdown({"repo": 5, "file": 3, "other": 2}, None)
    assert total == 2
    assert res == [{"type": "other", "count": 2}]


def test_residual_breakdown_with_schema_flags_offschema_and_other():
    schema = KGSchema(node_types=[NodeType(name="repo"), NodeType(name="file")])
    total, res = residual_breakdown({"repo": 5, "deployment": 4, "incident": 3, "other": 1}, schema)
    assert total == 8  # deployment + incident + other (repo is in schema)
    # sorted by count desc
    assert res[0] == {"type": "deployment", "count": 4}
    assert {"type": "incident", "count": 3} in res
    assert {"type": "other", "count": 1} in res


# --- assess_drift: too small -------------------------------------------------

def test_empty_when_graph_too_small():
    store = _FakeStore(by_type={"repo": 2})
    v = assess_drift(store, "kb", _cfg())
    assert v.mode == "empty"
    assert v.should_offer is False


# --- assess_drift: cold start ------------------------------------------------

def test_cold_start_offers_when_enough_and_not_yet_offered():
    store = _FakeStore(by_type={"repo": 6, "file": 6, "task": 4})  # 16 >= cold_start_min 12
    v = assess_drift(store, "kb", _cfg(), init_offered=False)
    assert v.mode == "cold_start"
    assert v.should_offer is True
    assert v.offer_line and "/brain2:schema" in v.offer_line


def test_cold_start_quiet_when_already_offered():
    store = _FakeStore(by_type={"repo": 6, "file": 6, "task": 4})
    v = assess_drift(store, "kb", _cfg(), init_offered=True)
    assert v.mode == "cold_start"
    assert v.should_offer is False
    assert v.offer_line is None


def test_cold_start_ok_when_below_threshold():
    # 10 nodes: >= min_nodes (8) so judged, but < cold_start_min (12) → ok, no offer
    store = _FakeStore(by_type={"repo": 5, "file": 5})
    v = assess_drift(store, "kb", _cfg(), init_offered=False)
    assert v.mode == "ok"
    assert v.should_offer is False


# --- assess_drift: drift -----------------------------------------------------

def test_drift_fires_when_residual_ratio_crosses():
    # schema covers repo/file; 10 off-schema of 20 total = 0.5 ratio, residual 10 >= floor 4
    store = _FakeStore(
        by_type={"repo": 6, "file": 4, "deployment": 6, "incident": 4},
        intent=_schema("repo", "file"),
    )
    v = assess_drift(store, "kb", _cfg(), drift_marker=0)
    assert v.mode == "drift"
    assert v.should_offer is True
    assert v.schema_version == 1
    assert v.residual == 10
    assert "don't fit schema v1" in v.offer_line


def test_drift_ok_when_residual_below_ratio():
    # only 2 off-schema of 20 = 0.1 ratio < drift_ratio 0.30 → ok
    store = _FakeStore(
        by_type={"repo": 10, "file": 8, "other": 2},
        intent=_schema("repo", "file"),
    )
    v = assess_drift(store, "kb", _cfg())
    assert v.mode == "ok"
    assert v.should_offer is False


def test_drift_rearm_quiet_until_growth():
    cfg = _cfg()
    store = _FakeStore(
        by_type={"repo": 6, "file": 4, "deployment": 6, "incident": 4},  # residual 10
        intent=_schema("repo", "file"),
    )
    # already offered at residual 10 → needs 10 + rearm_delta to re-fire
    v = assess_drift(store, "kb", cfg, drift_marker=10)
    assert v.mode == "drift"
    assert v.should_offer is False  # residual 10 < 10 + rearm_delta

    # drift intensifies past the re-arm threshold
    store2 = _FakeStore(
        by_type={"repo": 6, "file": 4, "deployment": 12, "incident": 6},  # residual 18
        intent=_schema("repo", "file"),
    )
    v2 = assess_drift(store2, "kb", cfg, drift_marker=10)
    assert v2.should_offer is True  # 18 >= 10 + rearm_delta (6)


def test_malformed_schema_treated_as_cold_start():
    store = _FakeStore(
        by_type={"repo": 6, "file": 6, "task": 4},
        intent={"version": 3, "schema": {"node_types": "not-a-list"}},  # malformed
    )
    v = assess_drift(store, "kb", _cfg(), init_offered=False)
    assert v.mode == "cold_start"
    assert v.should_offer is True
