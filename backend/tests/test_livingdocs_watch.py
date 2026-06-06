"""Unit tests for the Living Docs commit-boundary auto-capture (watch.py)."""

from __future__ import annotations

import os

from br8n.livingdocs.watch import derive_project_kb, run_once


def test_run_once_returns_none_when_auto_capture_disabled(monkeypatch):
    monkeypatch.setenv("BR8N_AUTO_CAPTURE", "0")
    # The gate short-circuits before any git/capture work happens.
    assert run_once(os.getcwd()) is None


def test_run_once_returns_none_when_living_docs_disabled(monkeypatch):
    monkeypatch.setenv("BR8N_LIVING_DOCS", "0")
    monkeypatch.setenv("BR8N_AUTO_CAPTURE", "1")
    assert run_once(os.getcwd()) is None


def test_derive_project_kb_falls_back_outside_git():
    # Non-repo path → project is the dir basename, kb defaults to "main".
    project, kb = derive_project_kb("/definitely/not/a/git/repo/xyz")
    assert project == "xyz"
    assert kb == "main"
