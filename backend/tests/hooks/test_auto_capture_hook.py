"""Tests for hooks/auto-capture.py — the SessionStart watcher launcher.

The hook lives outside backend/ and is not a package, so it's loaded by file
path via importlib. Tests are hermetic: no real subprocess is ever spawned (the
one launch test monkeypatches ``subprocess.Popen``).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Import the hook module from outside the package tree.
# ---------------------------------------------------------------------------

_HOOK_PATH = Path(__file__).parents[3] / "hooks" / "auto-capture.py"
_STOP_HOOK_PATH = Path(__file__).parents[3] / "hooks" / "auto-capture-stop.py"


def _load_hook(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"Cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


ac = _load_hook(_HOOK_PATH, "auto_capture")

# The worktree root (backend/tests/hooks/<file> → parents[3]) is a real git repo.
_REPO_ROOT = str(Path(__file__).parents[3])


def test_should_launch_respects_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "0")
    assert ac.should_launch(str(tmp_path)) is False  # gate off
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "1")
    monkeypatch.setenv("BRAIN2_LIVING_DOCS", "1")
    assert ac.should_launch("/definitely/not/a/git/repo/xyz") is False  # not a git repo


def test_should_launch_master_gate(monkeypatch):
    monkeypatch.setenv("BRAIN2_LIVING_DOCS", "0")
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "1")
    assert ac.should_launch(_REPO_ROOT) is False


def test_should_launch_true_in_git_repo(monkeypatch):
    monkeypatch.setenv("BRAIN2_LIVING_DOCS", "1")
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "1")
    assert ac.should_launch(_REPO_ROOT) is True


def test_launch_watcher_noop_when_gated(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "0")
    assert ac.launch_watcher(str(tmp_path)) is None


def test_paths_for_creates_brain2_dir(monkeypatch):
    monkeypatch.setenv("BRAIN2_LIVING_DOCS", "1")
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "1")
    stop_file, pid_file = ac.paths_for(_REPO_ROOT)
    assert stop_file.endswith(os.path.join(".brain2", ".watch.stop"))
    assert pid_file.endswith(os.path.join(".brain2", ".watch.pid"))
    assert os.path.isdir(os.path.dirname(stop_file))


def test_launch_watcher_spawns_module_with_env(monkeypatch):
    """When launchable, Popen is called with the watcher module + the right env."""
    monkeypatch.setenv("BRAIN2_LIVING_DOCS", "1")
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "1")

    calls = {}
    real_popen = ac.subprocess.Popen

    class _FakeProc:
        pid = 4242

    def _fake_popen(cmd, **kwargs):
        # Only intercept the watcher launch; let git's subprocess.run() work.
        if cmd[:1] == [sys.executable]:
            calls["cmd"] = cmd
            calls["kwargs"] = kwargs
            return _FakeProc()
        return real_popen(cmd, **kwargs)

    monkeypatch.setattr(ac.subprocess, "Popen", _fake_popen)

    pid = ac.launch_watcher(_REPO_ROOT)
    assert pid == 4242
    assert calls["cmd"] == [sys.executable, "-m", "brain2.livingdocs.watch"]
    env = calls["kwargs"]["env"]
    assert "BRAIN2_WATCH_CWD" in env
    assert "BRAIN2_WATCH_STOP" in env
    assert env["BRAIN2_WATCH_STOP"].endswith(os.path.join(".brain2", ".watch.stop"))
    # Detached so it survives the hook process.
    assert calls["kwargs"].get("start_new_session") is True
    # pid-file written.
    stop_file, pid_file = ac.paths_for(_REPO_ROOT)
    assert Path(pid_file).read_text().strip() == "4242"


def test_launch_watcher_removes_stale_stop_file(monkeypatch):
    monkeypatch.setenv("BRAIN2_LIVING_DOCS", "1")
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "1")
    stop_file, _pid_file = ac.paths_for(_REPO_ROOT)
    Path(stop_file).write_text("stop")
    assert os.path.exists(stop_file)

    real_popen = ac.subprocess.Popen

    class _FakeProc:
        pid = 7

    def _fake_popen(cmd, **kw):
        if cmd[:1] == [sys.executable]:
            return _FakeProc()
        return real_popen(cmd, **kw)

    monkeypatch.setattr(ac.subprocess, "Popen", _fake_popen)
    ac.launch_watcher(_REPO_ROOT)
    # Stale stop-file cleared so the fresh watcher won't immediately exit.
    assert not os.path.exists(stop_file)


def test_launch_watcher_never_raises(monkeypatch):
    monkeypatch.setenv("BRAIN2_LIVING_DOCS", "1")
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "1")

    real_popen = ac.subprocess.Popen

    def _boom(cmd, **kwargs):
        if cmd[:1] == [sys.executable]:
            raise OSError("nope")  # watcher spawn blows up
        return real_popen(cmd, **kwargs)  # git calls still work

    monkeypatch.setattr(ac.subprocess, "Popen", _boom)
    assert ac.launch_watcher(_REPO_ROOT) is None  # swallowed


def test_stop_watcher_writes_stop_file():
    stop_file, _pid_file = ac.paths_for(_REPO_ROOT)
    if os.path.exists(stop_file):
        os.remove(stop_file)
    ac.stop_watcher(_REPO_ROOT)
    assert os.path.exists(stop_file)
    assert Path(stop_file).read_text().strip() == "stop"


def test_stop_watcher_never_raises():
    # A path that can't exist as a repo root still must not raise.
    ac.stop_watcher("/definitely/not/a/git/repo/xyz")


def test_stop_hook_module_loads_and_imports_stop_watcher():
    stop_mod = _load_hook(_STOP_HOOK_PATH, "auto_capture_stop")
    assert callable(stop_mod.main)


import subprocess


def _tmp_git_repo(tmp_path) -> str:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    return str(tmp_path)


def test_install_post_commit_hook_creates(tmp_path):
    repo = _tmp_git_repo(tmp_path)
    assert ac.install_post_commit_hook(repo, "/usr/bin/python3") is True
    hook = Path(repo) / ".git" / "hooks" / "post-commit"
    text = hook.read_text()
    assert text.startswith("#!/bin/sh")
    assert ac._POST_COMMIT_MARKER in text
    assert "brain2.livingdocs.watch --once" in text
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


def _cleanup():
    stop_file, pid_file = ac.paths_for(_REPO_ROOT)
    for p in (stop_file, pid_file):
        if os.path.exists(p):
            os.remove(p)


def teardown_module(_module):
    _cleanup()
