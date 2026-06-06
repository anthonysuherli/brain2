"""KG-schema Store tests — versioned get/set intent via SQLiteStore.

No network, no mocks: SQLiteStore writes to a tmp_path file-backed DB so
WAL mode is exercised and the schema migration runs exactly once per store.
Each test gets a fresh store via the `store` fixture.
"""

from __future__ import annotations

import pytest

from br8n.store.sqlite import SQLiteStore


@pytest.fixture
def store(tmp_path):
    return SQLiteStore(str(tmp_path / "t.db"))


def test_set_then_get_kg_intent_versions(store):
    """set_kg_intent returns incrementing versions; get returns the latest."""
    org, kb = "org1", "kb1"
    s1 = store.set_kg_intent(org, kb, {"node_types": [], "competency_questions": ["q1"]})
    assert s1["version"] == 1
    s2 = store.set_kg_intent(org, kb, {"node_types": [], "competency_questions": ["q2"]})
    assert s2["version"] == 2
    latest = store.get_kg_intent(kb)
    assert latest is not None
    assert latest["schema"]["competency_questions"] == ["q2"]
    assert latest["version"] == 2


def test_get_kg_intent_none_when_unset(store):
    """get_kg_intent returns None for a kb_id with no schema set."""
    assert store.get_kg_intent("nope") is None


def test_versions_are_per_kb_not_global(store):
    """A second kb_id starts at version 1 independently."""
    org = "org1"
    store.set_kg_intent(org, "kb-a", {"node_types": ["Concept"]})
    store.set_kg_intent(org, "kb-a", {"node_types": ["Entity"]})
    # kb-b has never had a schema — its first set should get version 1
    s = store.set_kg_intent(org, "kb-b", {"node_types": ["Topic"]})
    assert s["version"] == 1


def test_set_returns_schema_content(store):
    """The returned dict contains the schema payload alongside version."""
    schema = {"node_types": ["Concept", "Paper"], "competency_questions": ["What is X?"]}
    result = store.set_kg_intent("org1", "kb1", schema)
    assert result["version"] == 1
    assert result["schema"]["node_types"] == ["Concept", "Paper"]
    assert result["schema"]["competency_questions"] == ["What is X?"]


def test_get_returns_schema_and_version(store):
    """get_kg_intent row carries both `schema` and `version` keys."""
    schema = {"node_types": ["A"], "competency_questions": ["q?"]}
    store.set_kg_intent("org1", "kb1", schema)
    row = store.get_kg_intent("kb1")
    assert row is not None
    assert "schema" in row
    assert "version" in row
    assert row["schema"]["node_types"] == ["A"]
