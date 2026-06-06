"""Tests for br8n.livingdocs.drift + the watcher's drift-triggered decision."""
from __future__ import annotations

import subprocess

import pytest

from br8n.livingdocs import drift, watch

_SNAP = """**Hypothesis**: fix the auth race

**Branch**: `main`

**Git diff stat**:
```
 backend/auth.py | 4 ++--
 backend/util.py | 2 +-
```

*Captured 2026-06-03 10:00:00 UTC — trigger: idle*"""


# ── pure helpers ──────────────────────────────────────────────────────────────
def test_parse_diff_stat_block():
    assert drift.parse_diff_stat_block(_SNAP) == {"backend/auth.py", "backend/util.py"}


def test_parse_diff_stat_block_empty():
    assert drift.parse_diff_stat_block(None) == set()
    assert drift.parse_diff_stat_block("no block here") == set()


def test_extract_hypothesis():
    assert drift.extract_hypothesis(_SNAP) == "fix the auth race"
    assert drift.extract_hypothesis("no hyp") is None


def test_compute_moved():
    assert drift.compute_moved({"a", "b"}, {"a", "b"}) == 0
    assert drift.compute_moved({"a", "b"}, {"a"}) == 1
    assert drift.compute_moved({"a"}, {"a", "b", "c"}) == 2


def test_is_drifted_threshold():
    assert drift.is_drifted(moved=0, commits=0) is False
    assert drift.is_drifted(moved=1, commits=0) is False  # below DRIFT_FILES_WARN
    assert drift.is_drifted(moved=2, commits=0) is True   # at threshold
    assert drift.is_drifted(moved=0, commits=1) is True   # a commit always drifts


# ── git-backed helpers ────────────────────────────────────────────────────────
def _make_repo(tmp):
    subprocess.run(["git", "init", str(tmp)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.email", "t@t.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.name", "T"], check=True, capture_output=True)
    (tmp / "a.py").write_text("x = 1")
    subprocess.run(["git", "-C", str(tmp), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp), "commit", "-m", "init"], check=True, capture_output=True)
    return tmp


def test_tracked_changed_files_excludes_untracked(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "a.py").write_text("x = 2")        # tracked, modified
    (repo / "new.py").write_text("y = 1")      # untracked
    result = drift.tracked_changed_files(str(repo))
    assert "a.py" in result
    assert "new.py" not in result


def test_commits_since(tmp_path):
    repo = _make_repo(tmp_path)
    assert drift.commits_since(str(repo), "2000-01-01T00:00:00Z") >= 1
    assert drift.commits_since(str(repo), "2999-01-01T00:00:00Z") == 0


# ── watcher decision (integration with local store) ───────────────────────────
@pytest.mark.asyncio
async def test_should_capture_first_anchor(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    repo = _make_repo(tmp_path / "repo")
    # No snapshot yet → first anchor.
    cap, hyp = watch.should_capture(str(repo), "repo", "main")
    assert cap is True
    assert hyp is None


async def _fake_embed_batch(texts):
    return [[0.0] * 1536 for _ in texts]


@pytest.mark.asyncio
async def test_should_capture_drift_then_quiet(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    import br8n.capture.service as capture_service
    monkeypatch.setattr(capture_service, "embed_batch", _fake_embed_batch)
    repo = _make_repo(tmp_path / "repo")
    # Anchor: capture the current (clean) state with a hypothesis.
    await watch.capture_once(
        "repo", "main", str(repo), branch="main",
        diff_stat=drift._git(str(repo), "diff", "HEAD", "--stat") or "",
        open_files=[], hypothesis="anchored intent",
    )
    # Immediately after, nothing changed → not drifted.
    cap, _ = watch.should_capture(str(repo), "repo", "main")
    assert cap is False
    # Now drift: change two tracked files.
    (repo / "a.py").write_text("x = 99")
    (repo / "b.py").write_text("z = 1")
    subprocess.run(["git", "-C", str(repo), "add", "b.py"], check=True, capture_output=True)
    cap, hyp = watch.should_capture(str(repo), "repo", "main")
    assert cap is True
    assert hyp == "anchored intent"  # carried forward
