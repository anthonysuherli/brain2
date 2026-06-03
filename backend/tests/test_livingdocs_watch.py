"""Unit tests for the Living Docs auto-capture watcher (pure functions)."""

from __future__ import annotations

import os

from brain2.livingdocs.watch import changed, fingerprint, run_watch


def test_changed_detects_diff():
    a = fingerprint(branch="main", diff_stat="1 file", open_files=["x.py"])
    b = fingerprint(branch="main", diff_stat="1 file", open_files=["x.py"])
    c = fingerprint(branch="main", diff_stat="2 files", open_files=["x.py"])
    assert changed(a, b) is False
    assert changed(a, c) is True
    assert changed(None, a) is True


def test_fingerprint_stable_regardless_of_open_files_order():
    a = fingerprint(branch="main", diff_stat="d", open_files=["a.py", "b.py"])
    b = fingerprint(branch="main", diff_stat="d", open_files=["b.py", "a.py"])
    assert changed(a, b) is False


def test_run_watch_returns_immediately_when_auto_capture_disabled(monkeypatch):
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "0")
    # Should return without doing any git/capture work. interval=0/max_ticks
    # are irrelevant because the gate short-circuits first.
    run_watch(os.getcwd(), interval=0, max_ticks=1)
