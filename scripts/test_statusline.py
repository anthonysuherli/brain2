"""Tests for brain2-statusline.py pure functions."""
import importlib.util, sys, os, pathlib

# Load the script as a module without executing main()
_SCRIPT = pathlib.Path(__file__).parent / "brain2-statusline.py"
spec = importlib.util.spec_from_file_location("statusline", _SCRIPT)
sl = importlib.util.module_from_spec(spec)
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
