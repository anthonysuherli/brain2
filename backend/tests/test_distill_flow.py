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
