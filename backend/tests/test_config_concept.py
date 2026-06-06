from br8n.config import get_config


def test_concept_config_defaults():
    c = get_config().concept
    assert c.synth_model
    assert 0.0 < c.reconcile_min_sim <= 1.0
    assert c.neighborhood_cap > 0
