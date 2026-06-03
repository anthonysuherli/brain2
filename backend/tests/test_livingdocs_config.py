from brain2.config import get_config


def test_living_docs_config_defaults():
    cfg = get_config().living_docs
    assert cfg.notes_dirname == "notes"
    assert cfg.docs_dirname == "docs"
    assert cfg.root_dirname == ".brain2"
    assert cfg.distill_debounce_n == 3
    assert cfg.distill_debounce_minutes == 60
    assert cfg.cluster_min_notes == 5
    assert cfg.watch_interval_seconds == 180
