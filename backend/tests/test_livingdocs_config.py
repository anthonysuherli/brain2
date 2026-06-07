from br8n.config import get_config


def test_living_docs_config_defaults():
    cfg = get_config().living_docs
    assert cfg.notes_dirname == "notes"
    assert cfg.docs_dirname == "docs"
    assert cfg.root_dirname == ".br8n"
    assert cfg.distill_debounce_n == 3
    assert cfg.distill_debounce_minutes == 60
    assert cfg.cluster_min_notes == 5


def test_timeline_config_defaults():
    from br8n.config import LivingDocsConfig

    cfg = LivingDocsConfig()
    assert cfg.timeline_dirname == "timeline"
    assert cfg.timeline_state_filename == "timeline-state.json"
    assert cfg.timeline_debounce_n == 3
    assert cfg.timeline_debounce_minutes == 60
    assert cfg.recent_days == 3
    assert cfg.week_days == 7
