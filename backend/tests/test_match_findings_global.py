"""Local-tier test for org-wide + category-filtered match_findings.

kb_id=None searches every KB in the org; `categories` narrows by category.
Vectors are nonzero only in dimension 0, so all are parallel (cosine
similarity 1.0) — membership is deterministic regardless of magnitude.
"""
from __future__ import annotations

from br8n.store.sqlite import SQLiteStore

DIM = 1536


def _vec(seed: float) -> list[float]:
    v = [0.0] * DIM
    v[0] = seed
    return v


async def test_match_findings_org_wide_and_category(tmp_path):
    store = SQLiteStore(str(tmp_path / "b.db"))
    await store.insert_findings(
        [
            {"kb_id": "kbA", "title": "a-note", "content": "alpha",
             "category": "note", "embedding": _vec(0.9)},
            {"kb_id": "kbA", "title": "a-web", "content": "alpha web",
             "category": "finding", "embedding": _vec(0.8)},
            {"kb_id": "kbJ", "title": "j1", "content": "journal alpha",
             "category": "journal", "embedding": _vec(0.95)},
        ]
    )
    q = _vec(1.0)

    # kb-scoped still works (unchanged behavior)
    only_a = await store.match_findings("kbA", q, 10, 0.0)
    assert {r["title"] for r in only_a} == {"a-note", "a-web"}

    # org-wide + category filter spans both KBs, excludes 'finding'
    both = await store.match_findings(None, q, 10, 0.0, categories=["journal", "note"])
    assert {r["title"] for r in both} == {"a-note", "j1"}

    store.close()
