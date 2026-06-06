"""Tests for hooks/auto-capture.py — the SessionStart commit-hook installer.

The hook lives outside backend/ and is not a package, so it's loaded by file
path via importlib. Tests are hermetic: they operate on throwaway git repos under
tmp_path and never spawn a background process (there is no watcher anymore).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Import the hook module from outside the package tree.
# ---------------------------------------------------------------------------

_HOOK_PATH = Path(__file__).parents[3] / "hooks" / "auto-capture.py"


def _load_hook(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"Cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


ac = _load_hook(_HOOK_PATH, "auto_capture")

# The worktree root (backend/tests/hooks/<file> → parents[3]) is a real git repo.
_REPO_ROOT = str(Path(__file__).parents[3])


def _tmp_git_repo(tmp_path) -> str:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    return str(tmp_path)


# ---------------------------------------------------------------------------
# Gate: should_install
# ---------------------------------------------------------------------------


def test_should_install_respects_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("BR8N_AUTO_CAPTURE", "0")
    assert ac.should_install(str(tmp_path)) is False  # gate off
    monkeypatch.setenv("BR8N_AUTO_CAPTURE", "1")
    monkeypatch.setenv("BR8N_LIVING_DOCS", "1")
    assert ac.should_install("/definitely/not/a/git/repo/xyz") is False  # not a git repo


def test_should_install_master_gate(monkeypatch):
    monkeypatch.setenv("BR8N_LIVING_DOCS", "0")
    monkeypatch.setenv("BR8N_AUTO_CAPTURE", "1")
    assert ac.should_install(_REPO_ROOT) is False


def test_should_install_true_in_git_repo(monkeypatch):
    monkeypatch.setenv("BR8N_LIVING_DOCS", "1")
    monkeypatch.setenv("BR8N_AUTO_CAPTURE", "1")
    assert ac.should_install(_REPO_ROOT) is True


# ---------------------------------------------------------------------------
# install(): gated installer used by main()
# ---------------------------------------------------------------------------


def test_install_noop_when_gated(monkeypatch, tmp_path):
    repo = _tmp_git_repo(tmp_path)
    monkeypatch.setenv("BR8N_AUTO_CAPTURE", "0")
    assert ac.install(repo) is False
    assert not (Path(repo) / ".git" / "hooks" / "post-commit").exists()


def test_install_writes_post_commit_hook_when_enabled(monkeypatch, tmp_path):
    repo = _tmp_git_repo(tmp_path)
    monkeypatch.setenv("BR8N_LIVING_DOCS", "1")
    monkeypatch.setenv("BR8N_AUTO_CAPTURE", "1")
    assert ac.install(repo) is True
    hook = Path(repo) / ".git" / "hooks" / "post-commit"
    assert ac._POST_COMMIT_MARKER in hook.read_text()


def test_install_never_raises(monkeypatch):
    monkeypatch.setenv("BR8N_LIVING_DOCS", "1")
    monkeypatch.setenv("BR8N_AUTO_CAPTURE", "1")
    # A non-repo path → should_install False → install returns False, never raises.
    assert ac.install("/definitely/not/a/git/repo/xyz") is False


# ---------------------------------------------------------------------------
# install_post_commit_hook(): the actual hook writer
# ---------------------------------------------------------------------------


def test_install_post_commit_hook_creates(tmp_path):
    repo = _tmp_git_repo(tmp_path)
    assert ac.install_post_commit_hook(repo, "/usr/bin/python3") is True
    hook = Path(repo) / ".git" / "hooks" / "post-commit"
    text = hook.read_text()
    assert text.startswith("#!/bin/sh")
    assert ac._POST_COMMIT_MARKER in text
    assert "br8n.livingdocs.watch --once" in text
    assert os.access(hook, os.X_OK)  # executable


def test_install_post_commit_hook_idempotent(tmp_path):
    repo = _tmp_git_repo(tmp_path)
    ac.install_post_commit_hook(repo, "/usr/bin/python3")
    ac.install_post_commit_hook(repo, "/usr/bin/python3")
    text = (Path(repo) / ".git" / "hooks" / "post-commit").read_text()
    assert text.count(ac._POST_COMMIT_MARKER) == 1  # not duplicated


def test_install_post_commit_hook_appends_to_existing(tmp_path):
    repo = _tmp_git_repo(tmp_path)
    hook = Path(repo) / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho 'user hook'\n")
    assert ac.install_post_commit_hook(repo, "/usr/bin/python3") is True
    text = hook.read_text()
    assert "echo 'user hook'" in text          # original preserved
    assert ac._POST_COMMIT_MARKER in text       # ours appended


def test_install_post_commit_hook_never_raises_non_repo():
    assert ac.install_post_commit_hook("/definitely/not/a/git/repo/xyz", "/usr/bin/python3") is False
