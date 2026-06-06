"""Tests for hooks/preamble-inject.py — the cached UserPromptSubmit preamble hook.

Loads the hook by file path (it lives outside backend/) and pins the cache dir so the
real ~/.br8n is never touched.
"""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_HOOK_PATH = Path(__file__).parents[3] / "hooks" / "preamble-inject.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("preamble_inject", _HOOK_PATH)
    assert spec is not None and spec.loader is not None, f"Cannot load {_HOOK_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


_hook = _load_hook()
derive_target = _hook.derive_target


@pytest.fixture(autouse=True)
def cache_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("BR8N_PREAMBLE_CACHE_DIR", str(tmp_path))
    return tmp_path


def _run_main_with_stdin(payload):
    sys.stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    try:
        _hook.main()
    finally:
        sys.stdin = sys.__stdin__


# --- _inject --------------------------------------------------------------

def test_inject_shape():
    out = _hook._inject("<preamble>x</preamble>")
    parsed = json.loads(out)
    assert parsed["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert parsed["hookSpecificOutput"]["additionalContext"] == "<preamble>x</preamble>"


# --- derive_target --------------------------------------------------------

def test_derive_target_none_for_non_git(tmp_path):
    assert derive_target(str(tmp_path)) is None


def test_derive_target_returns_basename_and_branch(tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "checkout", "-b", "feature/x"], cwd=str(tmp_path), check=True, capture_output=True
    )
    target = derive_target(str(tmp_path))
    assert target is not None
    project, kb = target
    assert project == tmp_path.name
    assert kb == "feature/x"


# --- main: cache hit / miss ----------------------------------------------

def test_main_cache_hit_injects_without_build(capsys, tmp_path):
    from br8n import preamble_cache

    preamble_cache.write("sess1", "repo", "dev", "<preamble>cached</preamble>")
    with (
        patch.object(_hook, "derive_target", return_value=("repo", "dev")),
        patch.object(_hook, "_build") as m_build,
    ):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "sess1"})
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["additionalContext"] == "<preamble>cached</preamble>"
    m_build.assert_not_called()


def test_main_cache_miss_builds_writes_injects(capsys, tmp_path):
    from br8n import preamble_cache

    with (
        patch.object(_hook, "derive_target", return_value=("repo", "dev")),
        patch.object(_hook, "_build", return_value="<preamble>fresh</preamble>"),
    ):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "sess2"})
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["additionalContext"] == "<preamble>fresh</preamble>"
    # Written to the cache for reuse next turn.
    assert preamble_cache.read("sess2", "repo", "dev") == "<preamble>fresh</preamble>"


def test_main_silent_when_build_none(capsys, tmp_path):
    from br8n import preamble_cache

    with (
        patch.object(_hook, "derive_target", return_value=("repo", "dev")),
        patch.object(_hook, "_build", return_value=None),
    ):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "sess3"})
    assert capsys.readouterr().out == ""
    assert preamble_cache.read("sess3", "repo", "dev") is None  # nothing cached


# --- main: suppress paths (unchanged from v1) -----------------------------

def test_main_silent_when_not_git(capsys, tmp_path):
    with patch.object(_hook, "derive_target", return_value=None):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "s"})
    assert capsys.readouterr().out == ""


def test_main_silent_when_gate_disabled(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_PREAMBLE_INJECT", "0")
    with patch.object(_hook, "derive_target", return_value=("repo", "dev")) as m:
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "s"})
    assert capsys.readouterr().out == ""
    m.assert_not_called()


def test_main_handles_malformed_stdin(capsys):
    _run_main_with_stdin("not json{{{")
    assert capsys.readouterr().out == ""


def test_main_handles_non_object_stdin(capsys):
    for payload in ("5", "[1, 2]", '"hello"', "null"):
        _run_main_with_stdin(payload)
        assert capsys.readouterr().out == ""


# --- _build fail-silent ---------------------------------------------------

def test_build_returns_none_on_error():
    """_build swallows a failed primer build and returns None (suppress)."""
    with patch(
        "br8n.agent.session_primer.build_session_primer",
        side_effect=RuntimeError("kb dev not found"),
    ):
        assert _hook._build("repo", "dev", "q") is None
