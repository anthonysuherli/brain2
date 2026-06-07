from br8n.livingdocs.paths import DocPaths
from br8n.livingdocs.state import (
    TimelineState,
    load_timeline_state,
    save_timeline_state,
    should_roll,
)


def test_timeline_state_roundtrip(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    st = load_timeline_state(p)
    assert st.events_since_pass == 0
    assert st.last_event_ts == ""
    st.events_since_pass = 2
    st.last_event_ts = "2026-06-07T10:00:00+00:00"
    st.last_event_id = "abc"
    st.last_appended_day = "2026-06-07"
    save_timeline_state(p, st)
    reloaded = load_timeline_state(p)
    assert reloaded.events_since_pass == 2
    assert reloaded.last_event_id == "abc"
    assert reloaded.last_appended_day == "2026-06-07"


def test_load_returns_default_when_absent(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    st = load_timeline_state(p)
    assert st.events_since_pass == 0
    assert st.last_pass_at == ""


def test_corrupt_timeline_state_falls_back(tmp_path):
    from br8n.livingdocs.paths import ensure_layout

    p = DocPaths(project_path=str(tmp_path), kb="main")
    ensure_layout(p)
    p.timeline_state_path.write_text("{ not valid json")
    st = load_timeline_state(p)  # must not raise
    assert st.events_since_pass == 0


def test_should_roll_count_threshold():
    st = TimelineState(events_since_pass=3)
    assert should_roll(st, debounce_n=3, debounce_minutes=60) is True


def test_should_roll_nothing_pending():
    st = TimelineState(events_since_pass=0, last_pass_at="2000-01-01T00:00:00+00:00")
    assert should_roll(st, debounce_n=3, debounce_minutes=60) is False


def test_should_roll_time_threshold():
    st = TimelineState(events_since_pass=1, last_pass_at="2026-01-01T00:00:00+00:00")
    assert should_roll(
        st, debounce_n=3, debounce_minutes=60, now_iso="2026-01-01T01:30:00+00:00"
    ) is True
    assert should_roll(
        st, debounce_n=3, debounce_minutes=60, now_iso="2026-01-01T00:30:00+00:00"
    ) is False


def test_should_roll_never_rolled_below_count_waits():
    st = TimelineState(events_since_pass=1, last_pass_at="")
    assert should_roll(st, debounce_n=3, debounce_minutes=60) is False
