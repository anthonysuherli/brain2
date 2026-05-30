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
    moved, commits = sl.compute_drift(captured, current, 0)
    assert moved == 2


def test_compute_drift_files_left():
    captured = {"a.py", "b.py", "c.py"}
    current  = {"a.py"}  # 2 files left the dirty set
    moved, commits = sl.compute_drift(captured, current, 0)
    assert moved == 2


def test_compute_drift_commits():
    moved, commits = sl.compute_drift(set(), set(), 3)
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
