"""Deterministic activity extraction — snapshot → nodes/edges.

The LLM task pass is disabled (``BRAIN2_ACTIVITY_LLM=0``) so these run offline:
``_task_label`` returns the raw hypothesis and no embedding/network is touched.
"""

from __future__ import annotations

import pytest

from brain2.capture.models import WorkspaceSnapshot
from brain2.knowledge_graph.activity import _parse_diff_files, _repo_label, activity_extract


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setenv("BRAIN2_ACTIVITY_LLM", "0")


def _snap(**kw) -> WorkspaceSnapshot:
    base = dict(
        project_path="/Users/me/code/brain2",
        trigger="manual",
        captured_at="2026-05-30T10:00:00Z",
        branch="dev",
    )
    base.update(kw)
    return WorkspaceSnapshot(**base)


def _by_type(extraction, t):
    return [n for n in extraction.nodes if n.type == t]


def _rels(extraction):
    return {e.relation for e in extraction.edges}


def test_repo_label_is_folder_basename():
    assert _repo_label(_snap(project_path="/Users/me/code/brain2")) == "brain2"
    assert _repo_label(_snap(project_path="brain2")) == "brain2"


def test_parse_diff_files():
    stat = " backend/a.py | 3 +++\n backend/b.py | 1 +\n 2 files changed, 4 insertions(+)"
    assert _parse_diff_files(stat) == ["backend/a.py", "backend/b.py"]


async def test_structural_nodes_and_edges():
    snap = _snap(
        cursor_file="store/base.py",
        open_files=["store/base.py", "store/sqlite.py", "README.md"],
        git_diff_stat=" store/base.py | 5 +++++",
        hypothesis="port KG builder to brain2",
    )
    ext = await activity_extract(snap, "finding-1")

    assert [n.label for n in _by_type(ext, "repo")] == ["brain2"]
    assert [n.label for n in _by_type(ext, "branch")] == ["dev"]
    assert len(_by_type(ext, "session")) == 1
    # cursor_file/diff file is "edited"; the other open files are "viewed".
    files = {n.label for n in _by_type(ext, "file")}
    assert files == {"store/base.py", "store/sqlite.py", "README.md"}
    # Task uses the raw hypothesis (LLM disabled).
    assert [n.label for n in _by_type(ext, "task")] == ["port KG builder to brain2"]

    assert {"on_repo", "on_branch", "in_repo", "edited", "viewed", "pursued"} <= _rels(ext)


async def test_session_grounded_in_finding():
    ext = await activity_extract(_snap(), "finding-xyz")
    session = _by_type(ext, "session")[0]
    assert session.grounded_in == ["finding-xyz"]


async def test_no_branch_no_branch_node():
    ext = await activity_extract(_snap(branch=None), "f1")
    assert _by_type(ext, "branch") == []
    assert "on_branch" not in _rels(ext)


async def test_no_hypothesis_no_task():
    ext = await activity_extract(_snap(hypothesis=None), "f1")
    assert _by_type(ext, "task") == []
    assert "pursued" not in _rels(ext)


async def test_edited_file_not_also_viewed():
    snap = _snap(cursor_file="a.py", open_files=["a.py", "b.py"])
    ext = await activity_extract(snap, "f1")
    edited = {e.target for e in ext.edges if e.relation == "edited"}
    viewed = {e.target for e in ext.edges if e.relation == "viewed"}
    # a.py is edited (cursor) and must not double as viewed.
    a_idx = next(i for i, n in enumerate(ext.nodes) if n.label == "a.py")
    assert a_idx in edited and a_idx not in viewed
