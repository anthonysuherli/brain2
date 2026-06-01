"""Tests for hooks/first-run-init.py — the SessionStart first-run guard.

All tests import the hook module directly so functions are testable without
running the hook as a subprocess.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the hook module from outside the package tree.
# ---------------------------------------------------------------------------

_HOOK_PATH = Path(__file__).parents[3] / "hooks" / "first-run-init.py"


def _load_hook():
    """Load the hook module by file path (it lives outside backend/)."""
    spec = importlib.util.spec_from_file_location("first_run_init", _HOOK_PATH)
    assert spec is not None and spec.loader is not None, f"Cannot load {_HOOK_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


_hook = _load_hook()
repo_identity = _hook.repo_identity
derive_project_kb = _hook.derive_project_kb
build_directive = _hook.build_directive
check_kb_exists = _hook.check_kb_exists


# ---------------------------------------------------------------------------
# repo_identity
# ---------------------------------------------------------------------------


def test_repo_identity_returns_none_for_non_git(tmp_path):
    """A plain directory (no .git) should return None."""
    identity = repo_identity(str(tmp_path))
    assert identity is None


def test_repo_identity_returns_path_for_git_repo_without_remote(tmp_path):
    """A git repo with no remote should fall back to the repo root path."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    identity = repo_identity(str(tmp_path))
    assert identity is not None
    assert str(tmp_path) in identity or tmp_path.name in identity


def test_repo_identity_uses_remote_origin(tmp_path):
    """When origin is set the identity is derived from the remote URL."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/my-repo.git"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    identity = repo_identity(str(tmp_path))
    assert identity is not None
    assert "my-repo" in identity
    assert "acme" in identity
    assert ".git" not in identity


def test_repo_identity_normalizes_ssh_url(tmp_path):
    """SSH shorthand remote URLs should be normalised to host/path form."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:user/cool-project.git"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    identity = repo_identity(str(tmp_path))
    assert identity is not None
    assert "cool-project" in identity
    assert ".git" not in identity
    # Should be lowercase
    assert identity == identity.lower()


# ---------------------------------------------------------------------------
# derive_project_kb
# ---------------------------------------------------------------------------


def test_derive_project_kb_from_cwd(tmp_path):
    """When the repo has no remote the project name is the cwd basename."""
    project, kb = derive_project_kb(str(tmp_path))
    assert project == tmp_path.name or project == tmp_path.name.replace("_", "-")
    assert kb == "main"


def test_derive_project_kb_kb_is_always_main(tmp_path):
    """kb must always be 'main' regardless of repo state."""
    _, kb = derive_project_kb(str(tmp_path))
    assert kb == "main"


def test_derive_project_kb_cleans_special_chars(tmp_path):
    """Special characters in directory names are replaced with hyphens."""
    special = tmp_path / "my_repo.test"
    special.mkdir()
    project, _ = derive_project_kb(str(special))
    assert "_" not in project
    assert "." not in project


# ---------------------------------------------------------------------------
# build_directive
# ---------------------------------------------------------------------------


def test_build_directive_mentions_project_and_init():
    d = build_directive("my-repo", "main")
    assert "my-repo" in d
    assert "background" in d.lower()
    assert "project-init" in d


def test_build_directive_mentions_schema_wizard():
    d = build_directive("my-repo", "main")
    assert "kg-schema-wizard" in d


def test_build_directive_mentions_kb_name():
    d = build_directive("alpha", "session")
    assert "alpha" in d
    assert "session" in d


def test_build_directive_mentions_mark_init_offered():
    """The directive must reference the stamp call so Claude knows to call it."""
    d = build_directive("my-repo", "main")
    assert "brain2_mark_init_offered" in d


def test_build_directive_references_print_line():
    """The directive must tell Claude to print a visible line for the user."""
    d = build_directive("my-repo", "main")
    assert "Initializing brain2" in d


# ---------------------------------------------------------------------------
# check_kb_exists
# ---------------------------------------------------------------------------


def test_check_kb_exists_returns_true_when_tenant_resolves():
    with patch(
        "brain2.interfaces.mcp.tenancy.resolve_tenant",
        return_value=MagicMock(),
    ):
        result = check_kb_exists("my-project", "main")
    assert result is True


def test_check_kb_exists_returns_false_when_not_found():
    with patch(
        "brain2.interfaces.mcp.tenancy.resolve_tenant",
        side_effect=RuntimeError("kb main not found"),
    ):
        result = check_kb_exists("my-project", "main")
    assert result is False


def test_check_kb_exists_returns_none_on_backend_error():
    """A non-'not found' RuntimeError returns None (fail-closed)."""
    with patch(
        "brain2.interfaces.mcp.tenancy.resolve_tenant",
        side_effect=RuntimeError("connection refused"),
    ):
        result = check_kb_exists("my-project", "main")
    assert result is None


def test_check_kb_exists_returns_none_on_unexpected_exception():
    """Any unexpected exception returns None (fail-closed, not False)."""
    with patch(
        "brain2.interfaces.mcp.tenancy.resolve_tenant",
        side_effect=ImportError("module not found"),
    ):
        result = check_kb_exists("my-project", "main")
    assert result is None


# ---------------------------------------------------------------------------
# main() integration — stdout / silence
# ---------------------------------------------------------------------------


def test_main_emits_directive_for_first_run(capsys, tmp_path):
    """main() should print JSON additionalContext when KB does not exist."""
    with (
        patch.object(_hook, "repo_identity", return_value="github.com/user/repo"),
        patch.object(_hook, "derive_project_kb", return_value=("repo", "main")),
        patch.object(_hook, "check_kb_exists", return_value=False),
    ):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert "additionalContext" in out
    assert "repo" in out["additionalContext"]


def test_main_silent_when_kb_exists(capsys, tmp_path):
    """main() should produce no output when the KB already exists."""
    with (
        patch.object(_hook, "repo_identity", return_value="github.com/user/repo"),
        patch.object(_hook, "derive_project_kb", return_value=("repo", "main")),
        patch.object(_hook, "check_kb_exists", return_value=True),
    ):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_silent_when_not_git_repo(capsys, tmp_path):
    """main() should produce no output for non-git directories."""
    with patch.object(_hook, "repo_identity", return_value=None):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_silent_when_backend_unreachable(capsys, tmp_path):
    """main() should be silent (fail-closed) when backend check returns None."""
    with (
        patch.object(_hook, "repo_identity", return_value="github.com/user/repo"),
        patch.object(_hook, "derive_project_kb", return_value=("repo", "main")),
        patch.object(_hook, "check_kb_exists", return_value=None),
    ):
        hook_input = json.dumps({"cwd": str(tmp_path)})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_handles_session_cwd_key(capsys, tmp_path):
    """main() accepts the nested session.cwd payload shape."""
    with (
        patch.object(_hook, "repo_identity", return_value=None),
    ):
        hook_input = json.dumps({"session": {"cwd": str(tmp_path)}})
        sys.stdin = __import__("io").StringIO(hook_input)
        try:
            _hook.main()
        finally:
            sys.stdin = sys.__stdin__

    # repo_identity returns None → silent exit (correct behaviour)
    captured = capsys.readouterr()
    assert captured.out == ""
