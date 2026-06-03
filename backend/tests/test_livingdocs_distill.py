"""Tests for the curated doc-tree distiller (taxonomy inference + writer)."""
from __future__ import annotations

from brain2.livingdocs.distill import plan_layout


def test_flat_until_min_notes():
    notes = [{"title": f"n{i}", "topic": None} for i in range(3)]
    layout = plan_layout(notes, cluster_min_notes=5, schema=None)
    assert all(entry["folder"] == "" for entry in layout)  # flat


def test_clusters_when_enough_and_topics_present():
    notes = [{"title": "auth race", "topic": "auth"} for _ in range(3)] + \
            [{"title": "ui tweak", "topic": "ui"} for _ in range(3)]
    layout = plan_layout(notes, cluster_min_notes=5, schema=None)
    folders = {e["folder"] for e in layout}
    assert "auth" in folders and "ui" in folders


def test_schema_overrides_inferred():
    notes = [{"title": "x", "topic": "auth"}]
    layout = plan_layout(notes, cluster_min_notes=1, schema=["security", "ui"])
    assert all(e["folder"] in {"security", "ui", ""} for e in layout)
