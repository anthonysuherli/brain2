from br8n.livingdocs.timeline import (
    TimelineEvent,
    _event_day,
    _event_line,
    append_all_time,
    render_window,
)
from br8n.livingdocs.paths import DocPaths


def _ev(ts, kind, title, gist, _id):
    return TimelineEvent(ts=ts, kind=kind, title=title, gist=gist, id=_id)


def test_event_line_and_day():
    e = _ev("2026-06-07T14:30:00+00:00", "note", "Storage choice", "Chose SQLite", "f1")
    assert _event_day(e) == "2026-06-07"
    line = _event_line(e)
    assert "14:30" in line
    assert "note" in line
    assert "Storage choice" in line
    assert "Chose SQLite" in line


def test_append_all_time_writes_header_and_day_divider_once(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    events = [
        _ev("2026-06-07T09:00:00+00:00", "note", "A", "ga", "1"),
        _ev("2026-06-07T11:00:00+00:00", "capture", "B", "gb", "2"),
        _ev("2026-06-08T08:00:00+00:00", "journal", "C", "gc", "3"),
    ]
    last_day = append_all_time(p, "br8n", "main", events, last_appended_day="")
    text = p.timeline_dir.joinpath("all-time.md").read_text()
    assert text.startswith("# Activity — br8n/main")
    assert text.count("## 2026-06-07") == 1  # single divider for the day
    assert text.count("## 2026-06-08") == 1
    assert last_day == "2026-06-08"
    # newest at the bottom (ascending): C's line comes after A's line
    assert text.index("\nA — ".replace("A — ", "")) >= 0  # smoke
    assert text.index(" · A —") < text.index(" · C —")


def test_append_all_time_is_additive_not_rewritten(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    first = [_ev("2026-06-07T09:00:00+00:00", "note", "First", "g1", "1")]
    day = append_all_time(p, "br8n", "main", first, last_appended_day="")
    second = [_ev("2026-06-07T10:00:00+00:00", "note", "Second", "g2", "2")]
    append_all_time(p, "br8n", "main", second, last_appended_day=day)
    text = p.timeline_dir.joinpath("all-time.md").read_text()
    assert "First" in text and "Second" in text   # first pass preserved
    assert text.count("# Activity — br8n/main") == 1  # header written once
    assert text.count("## 2026-06-07") == 1           # divider not duplicated


def test_render_window_groups_by_day_plain_headers(tmp_path):
    events = [
        _ev("2026-06-07T09:00:00+00:00", "note", "A", "ga", "1"),
        _ev("2026-06-08T08:00:00+00:00", "note", "B", "gb", "2"),
    ]
    out = render_window("recent", events, day_headers=None)  # None → plain dividers
    assert "## 2026-06-07" in out and "## 2026-06-08" in out
    assert out.index("## 2026-06-07") < out.index("## 2026-06-08")  # ascending


def test_render_window_uses_llm_day_headers_when_given(tmp_path):
    events = [_ev("2026-06-07T09:00:00+00:00", "note", "A", "ga", "1")]
    out = render_window("recent", events, day_headers={"2026-06-07": "Set up storage"})
    assert "## 2026-06-07 — Set up storage" in out
