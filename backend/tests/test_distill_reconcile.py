from br8n.config import get_config
from br8n.knowledge_graph.distill import ConceptCandidate, reconcile_action


def _cfg():
    return get_config().concept


def test_reconcile_new_when_no_neighbor():
    cand = ConceptCandidate(claim="fresh idea", evidence=["f1"])
    action = reconcile_action(cand, nearest=None, similarity=0.0, cfg=_cfg())
    assert action.kind == "new"


def test_reconcile_reinforce_on_high_similarity():
    cand = ConceptCandidate(claim="x compounds", evidence=["f2"])
    nearest = {"id": "n1", "label": "x compounds"}
    action = reconcile_action(cand, nearest=nearest, similarity=0.95, cfg=_cfg())
    assert action.kind == "reinforce"
    assert action.node_id == "n1"


def test_reconcile_new_when_similar_vector_but_different_claim():
    cand = ConceptCandidate(claim="totally different topic", evidence=["f3"])
    nearest = {"id": "n1", "label": "x compounds y in systems"}
    action = reconcile_action(cand, nearest=nearest, similarity=0.79, cfg=_cfg())
    assert action.kind == "new"
