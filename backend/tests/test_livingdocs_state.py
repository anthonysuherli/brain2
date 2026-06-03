from brain2.livingdocs.paths import DocPaths
from brain2.livingdocs.state import load_state, save_state, DocsState, should_distill


def test_state_roundtrip_and_debounce(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    st = load_state(p)
    assert st.notes_since_distill == 0
    st.notes_since_distill = 3
    save_state(p, st)
    assert load_state(p).notes_since_distill == 3
    # N threshold reached
    assert should_distill(st, debounce_n=3, debounce_minutes=60) is True
    st.notes_since_distill = 1
    assert should_distill(st, debounce_n=3, debounce_minutes=60, now_iso="1970-01-01T00:00:00+00:00") is False


def test_load_returns_default_when_absent(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    st = load_state(p)
    assert st.notes_since_distill == 0
    assert st.taxonomy == {}
    assert st.last_distill_at == ""


def test_corrupt_state_file_falls_back(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    from brain2.livingdocs.paths import ensure_layout
    ensure_layout(p)
    p.state_path.write_text("{ not valid json")
    st = load_state(p)  # must not raise
    assert st.notes_since_distill == 0


def test_time_threshold_triggers_distill(tmp_path):
    st = DocsState(notes_since_distill=1, last_distill_at="2026-01-01T00:00:00+00:00")
    # 90 minutes later, debounce_minutes=60 → elapsed >= threshold
    assert should_distill(
        st, debounce_n=3, debounce_minutes=60, now_iso="2026-01-01T01:30:00+00:00"
    ) is True
    # 30 minutes later → below threshold
    assert should_distill(
        st, debounce_n=3, debounce_minutes=60, now_iso="2026-01-01T00:30:00+00:00"
    ) is False


def test_nothing_pending_never_distills(tmp_path):
    st = DocsState(notes_since_distill=0, last_distill_at="2000-01-01T00:00:00+00:00")
    assert should_distill(st, debounce_n=3, debounce_minutes=60) is False


def test_robust_to_trailing_z_and_naive(tmp_path):
    # 'Z' suffix
    st = DocsState(notes_since_distill=1, last_distill_at="2026-01-01T00:00:00Z")
    assert should_distill(
        st, debounce_n=3, debounce_minutes=60, now_iso="2026-01-01T02:00:00Z"
    ) is True
    # naive timestamps (no tz) — assume UTC, don't raise
    st2 = DocsState(notes_since_distill=1, last_distill_at="2026-01-01T00:00:00")
    assert should_distill(
        st2, debounce_n=3, debounce_minutes=60, now_iso="2026-01-01T02:00:00"
    ) is True
