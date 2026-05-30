"""Tests for brain2-statusline.py pure functions."""
import importlib.util
import importlib.abc
import pathlib
import json
import os

# Load the script as a module without executing main()
_SCRIPT = pathlib.Path(__file__).parent / "brain2-statusline.py"
spec = importlib.util.spec_from_file_location("statusline", _SCRIPT)
assert spec is not None and spec.loader is not None
sl = importlib.util.module_from_spec(spec)
assert isinstance(spec.loader, importlib.abc.Loader)
spec.loader.exec_module(sl)


# ── parse_diff_stat_block ──────────────────────────────────────────────────

def test_parse_diff_stat_basic():
    content = (
        "**Hypothesis**: fix the thing\n\n"
        "**Git diff stat**:\n```\n"
        " src/foo.py | 3 +++\n"
        " src/bar.py | 1 -\n"
        " 2 files changed, 3 insertions(+), 1 deletion(-)\n"
        "```\n"
    )
    assert sl.parse_diff_stat_block(content) == {"src/foo.py", "src/bar.py"}


def test_parse_diff_stat_empty_content():
    assert sl.parse_diff_stat_block("") == set()
    assert sl.parse_diff_stat_block(None) == set()


def test_parse_diff_stat_no_block():
    assert sl.parse_diff_stat_block("**Hypothesis**: just a thought") == set()


def test_parse_diff_stat_truncated():
    content = (
        "**Git diff stat**:\n```\n"
        " a/b/c.py | 5 +++++\n"
        " x/y/z.ts | 2 --\n"
        "```\n"
    )
    assert sl.parse_diff_stat_block(content) == {"a/b/c.py", "x/y/z.ts"}


def test_parse_diff_stat_plus_n_more():
    content = (
        "**Git diff stat**:\n```\n"
        " src/alpha.py | 1 +\n"
        " ... and 3 more\n"
        "```\n"
    )
    result = sl.parse_diff_stat_block(content)
    assert "src/alpha.py" in result
    assert "... and 3 more" not in result


# ── compute_drift ──────────────────────────────────────────────────────────

def test_compute_drift_identical():
    files = {"a.py", "b.py"}
    moved, commits = sl.compute_drift(files, files, 0)
    assert moved == 0
    assert commits == 0


def test_compute_drift_files_entered():
    captured = {"a.py"}
    current  = {"a.py", "b.py", "c.py"}  # 2 new files
    moved, _ = sl.compute_drift(captured, current, 0)
    assert moved == 2


def test_compute_drift_files_left():
    captured = {"a.py", "b.py", "c.py"}
    current  = {"a.py"}  # 2 files left the dirty set
    moved, _ = sl.compute_drift(captured, current, 0)
    assert moved == 2


def test_compute_drift_commits():
    _, commits = sl.compute_drift(set(), set(), 3)
    assert commits == 3


def test_compute_drift_combined():
    captured = {"a.py", "b.py"}
    current  = {"b.py", "c.py"}  # a left, c entered = 2 moved
    moved, commits = sl.compute_drift(captured, current, 1)
    assert moved == 2
    assert commits == 1


# ── classify ──────────────────────────────────────────────────────────────

def test_classify_no_capture():
    state = sl.classify(snapshot=None, age_secs=0, moved=0, commits_since=0)
    assert state == "NO_CAPTURE"


def test_classify_fresh():
    state = sl.classify(snapshot={"hyp": "x"}, age_secs=100, moved=0, commits_since=0)
    assert state == "FRESH"


def test_classify_drifted_by_files():
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=100,
        moved=sl.DRIFT_FILES_WARN,   # exactly at threshold
        commits_since=0,
    )
    assert state == "DRIFTED"


def test_classify_drifted_by_commits():
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=100,
        moved=0,
        commits_since=1,
    )
    assert state == "DRIFTED"


def test_classify_drifted_beats_idle():
    # Age past IDLE threshold but also has commits — should be DRIFTED, not IDLE
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=sl.IDLE_AGE + 100,
        moved=0,
        commits_since=2,
    )
    assert state == "DRIFTED"


def test_classify_idle():
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=sl.IDLE_AGE + 100,
        moved=0,
        commits_since=0,
    )
    assert state == "IDLE"


def test_classify_stale_but_not_idle_is_fresh():
    # Past STALE_AGE but under IDLE_AGE, no drift → FRESH
    state = sl.classify(
        snapshot={"hyp": "x"},
        age_secs=sl.STALE_AGE + 60,
        moved=0,
        commits_since=0,
    )
    assert state == "FRESH"


# ── render_line1 ──────────────────────────────────────────────────────────

def _strip(s):
    """Strip ANSI codes for assertion."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)


def test_render_line1_with_hypothesis():
    line, _ = sl.render_line1("brain2", "dev", "fix the thing", width=80)
    line = _strip(line)
    assert "🧠 brain2" in line
    assert "▶ dev" in line
    assert '"fix the thing"' in line


def test_render_line1_no_hypothesis():
    line, _ = sl.render_line1("brain2", "dev", None, width=80)
    line = _strip(line)
    assert "▶ dev" in line
    assert '"' not in line  # no empty quotes


def test_render_line1_truncates_hypothesis():
    long_hyp = "x" * 100
    line, hyp_fits = sl.render_line1("brain2", "dev", long_hyp, width=60)
    line = _strip(line)
    assert "…" in line
    assert hyp_fits is False


# ── render_line2 ──────────────────────────────────────────────────────────

def test_render_line2_no_capture():
    line = _strip(sl.render_line2("NO_CAPTURE", age_secs=0, moved=0, commits=0,
                                   hypothesis=None, hyp_fits=True, utf8=False))
    assert "no capture" in line
    assert "/brain2:capture" in line


def test_render_line2_fresh_no_action():
    line = _strip(sl.render_line2("FRESH", age_secs=60, moved=0, commits=0,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "fresh" in line
    assert "/resume" not in line
    assert "/brain2:capture" not in line


def test_render_line2_fresh_shows_age():
    line = _strip(sl.render_line2("FRESH", age_secs=300, moved=0, commits=0,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "5m" in line


def test_render_line2_drifted_has_action():
    line = _strip(sl.render_line2("DRIFTED", age_secs=1200, moved=3, commits=1,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "drifted" in line
    assert "/resume" in line


def test_render_line2_drifted_ascii_glyphs():
    line = _strip(sl.render_line2("DRIFTED", age_secs=600, moved=3, commits=1,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "f3" in line   # ASCII fallback for ╓3
    assert "c1" in line   # ASCII fallback for ⎇1


def test_render_line2_drifted_utf8_glyphs():
    line = _strip(sl.render_line2("DRIFTED", age_secs=600, moved=3, commits=1,
                                   hypothesis="x", hyp_fits=True, utf8=True))
    assert "╓3" in line
    assert "⎇1" in line


def test_render_line2_drifted_omits_zero_glyphs():
    line = _strip(sl.render_line2("DRIFTED", age_secs=600, moved=0, commits=1,
                                   hypothesis="x", hyp_fits=True, utf8=True))
    assert "╓" not in line  # 0 files moved — omit


def test_render_line2_idle_quiet():
    line = _strip(sl.render_line2("IDLE", age_secs=90000, moved=0, commits=0,
                                   hypothesis="x", hyp_fits=True, utf8=False))
    assert "idle" in line
    assert "/resume" not in line
    assert "/brain2:capture" not in line


def test_render_line2_idle_echoes_hyp_when_truncated():
    line = _strip(sl.render_line2("IDLE", age_secs=90000, moved=0, commits=0,
                                   hypothesis="refactor adapter", hyp_fits=False, utf8=False))
    assert "refactor adapter" in line


def test_render_line2_idle_no_echo_when_fits():
    line = _strip(sl.render_line2("IDLE", age_secs=90000, moved=0, commits=0,
                                   hypothesis="refactor adapter", hyp_fits=True, utf8=False))
    assert "refactor adapter" not in line


# ── live_diff_files + commits_since_capture (integration) ─────────────────
import subprocess
import pathlib as _pathlib


def _make_repo(tmp: _pathlib.Path) -> _pathlib.Path:
    """Create a minimal git repo in tmp with one initial commit."""
    subprocess.run(["git", "init", str(tmp)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.email", "test@test.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.name", "Test"],
                   check=True, capture_output=True)
    (tmp / "README.md").write_text("hi")
    subprocess.run(["git", "-C", str(tmp), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "commit", "-m", "init"],
                   check=True, capture_output=True)
    return tmp


def test_live_diff_files_empty(tmp_path):
    repo = _make_repo(tmp_path)
    result = sl.live_diff_files(str(repo))
    assert result == set()


def test_live_diff_files_dirty(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "foo.py").write_text("x = 1")
    result = sl.live_diff_files(str(repo))
    assert "foo.py" in result


def test_commits_since_capture_zero(tmp_path):
    from datetime import datetime, timezone
    repo = _make_repo(tmp_path)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    count = sl.commits_since_capture(str(repo), now_iso)
    assert count == 0


def test_commits_since_capture_nonzero(tmp_path):
    repo = _make_repo(tmp_path)
    past_iso = "2000-01-01T00:00:00Z"
    count = sl.commits_since_capture(str(repo), past_iso)
    assert count >= 1  # at least the "init" commit
