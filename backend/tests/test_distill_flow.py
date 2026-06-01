import pytest

import brain2.knowledge_graph.distill as d
from brain2.store import SQLiteStore

DIM = 1536


def _vec(seed):
    v = list(seed) + [0.0] * (DIM - len(seed))
    return v[:DIM]


@pytest.fixture
def store():
    return SQLiteStore(":memory:")


async def _seed_findings(store, kb_id):
    await store.insert_findings([
        {"org_id": "local", "kb_id": kb_id, "project_id": "p", "title": "X",
         "content": "x details", "category": "general", "confidence": 0.7,
         "embedding": _vec([1.0, 0.0])},
        {"org_id": "local", "kb_id": kb_id, "project_id": "p", "title": "Y",
         "content": "y details", "category": "general", "confidence": 0.7,
         "embedding": _vec([0.9, 0.1])},
    ])


async def test_distill_kb_creates_concept_with_evidence(monkeypatch, store):
    kb = "akb"
    await _seed_findings(store, kb)

    async def fake_synth(findings, cfg):
        return [d.ConceptCandidate(claim="X and Y compound", body="why", evidence=["irrelevant"])]
    monkeypatch.setattr(d, "synthesize", fake_synth)
    monkeypatch.setattr(d, "_embed_claims", lambda claims: [_vec([0.0, 1.0]) for _ in claims])

    n = await d.distill_kb(store, org_id="local", kb_id=kb)
    assert n["concepts_created"] == 1

    concepts = store.list_kg_nodes(kb, type="concept")
    assert len(concepts) == 1
    assert concepts[0]["label"] == "X and Y compound"
    assert concepts[0]["grounded_in"]   # evidence bound from selected findings


async def test_distill_kb_reinforces_on_second_pass(monkeypatch, store):
    kb = "akb"
    await _seed_findings(store, kb)

    async def fake_synth(findings, cfg):
        return [d.ConceptCandidate(claim="X and Y compound", body="v", evidence=[])]
    monkeypatch.setattr(d, "synthesize", fake_synth)
    monkeypatch.setattr(d, "_embed_claims", lambda claims: [_vec([0.0, 1.0]) for _ in claims])

    await d.distill_kb(store, org_id="local", kb_id=kb)
    await d.distill_kb(store, org_id="local", kb_id=kb)

    concepts = store.list_kg_nodes(kb, type="concept")
    assert len(concepts) == 1   # reinforced, not duplicated
    assert concepts[0]["properties"].get("version", 1) >= 2


async def test_reinforce_preserves_evidence_past_recency_window(monkeypatch, store):
    """Regression for I-1: a concept that has fallen OUT of the default
    list_kg_nodes window must still have its prior evidence UNIONED (not wiped) on
    reinforce. We force the window-miss by upserting 55 OTHER concept nodes after
    pass 1, then re-distill the SAME claim (same stub embedding) over a DIFFERENT
    evidence set so a wipe-vs-union is observable: the union must keep pass-1 ids,
    a wipe would drop them."""
    kb = "akb"

    # Pass 1 grounds in findings {f1, f2}; pass 2 grounds in disjoint {f3, f4}.
    pass1 = [{"id": "f1", "content": "a"}, {"id": "f2", "content": "b"}]
    pass2 = [{"id": "f3", "content": "c"}, {"id": "f4", "content": "d"}]
    selections = iter([pass1, pass2])

    async def fake_select(store, kb_id, cfg):
        return next(selections)
    monkeypatch.setattr(d, "_select_findings", fake_select)

    async def fake_synth(findings, cfg):
        return [d.ConceptCandidate(claim="X and Y compound", body="v", evidence=[])]
    monkeypatch.setattr(d, "synthesize", fake_synth)
    # Original concept + re-distilled claim share this vector so the match maps back.
    monkeypatch.setattr(d, "_embed_claims", lambda claims: [_vec([0.0, 1.0]) for _ in claims])

    # First pass: create the concept grounded in {f1, f2}.
    await d.distill_kb(store, org_id="local", kb_id=kb)
    concepts = store.list_kg_nodes(kb, type="concept")
    assert len(concepts) == 1
    target_id = concepts[0]["id"]
    assert set(concepts[0]["grounded_in"]) == {"f1", "f2"}

    # Push the original OUT of the default list_kg_nodes window (cap 50) with 55
    # distinct dummy concepts. A different vector ([0.3, 0.3]) keeps them from
    # outranking the original on cosine similarity to the [0.0, 1.0] claim.
    await store.upsert_kg_nodes(kb, [
        {"org_id": "local", "type": "concept", "label": f"dummy concept {i}",
         "properties": {"body": "z", "version": 1}, "grounded_in": [],
         "embedding": _vec([0.3, 0.3])}
        for i in range(55)
    ])
    windowed = store.list_kg_nodes(kb, type="concept")  # default cap 50
    assert target_id not in {c["id"] for c in windowed}  # original is window-missed

    # Second pass: same claim → reinforces the original by id (not the dummies),
    # over disjoint evidence {f3, f4}.
    await d.distill_kb(store, org_id="local", kb_id=kb)

    after = store.get_kg_node(kb, target_id)
    assert after is not None
    # Evidence was UNIONED, not wiped: pass-1 ids survive alongside pass-2 ids.
    assert set(after["grounded_in"]) == {"f1", "f2", "f3", "f4"}
    # And the version was bumped on the real node.
    assert int(after["properties"].get("version", 1)) >= 2
