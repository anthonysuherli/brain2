# brain2 Journal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cross-project, write-anytime, semantically-searchable personal journal to brain2, reusing its existing OpenAI embeddings + vector search.

**Architecture:** A journal entry is a brain2 finding (`category="journal"`) under a reserved, repo-independent scope (`__journal__`), stored in the same `~/.brain2/brain.db`. New thin write/search paths sit beside the existing note path; the one infra change extends `match_findings` to support org-wide (`kb_id=None`) + category-filtered search so `scope='both'` can span the journal and every project's notes.

**Tech Stack:** Python 3.11, FastMCP, SQLite + sqlite-vec (local tier), Supabase/Postgres + pgvector (cloud tier), OpenAI `text-embedding-3-small` (1536-dim). Tests: pytest (`asyncio_mode=auto`), run from `backend/`.

**Spec:** `docs/plans/2026-06-03-brain2-journal-design.md` (commit `dd3a7b7`).

**Conventions (read before starting):**
- All commands run from `/Users/suherli/Repositories/brain2/backend` unless noted.
- Tests wire the real `SQLiteStore` via `BRAIN2_BACKEND=local` + a tmp `BRAIN2_DB_PATH`; only the embedder is faked (no OpenAI call). Clear `brain2.store._local_stores` before and after so the tmp DB is honored. Mirror `backend/tests/test_note_tool.py`.
- `from __future__ import annotations` at the top of every new module; type hints everywhere; ruff line-length 100.
- Branch is `dev` (not the default `main`); commit directly to `dev`.

---

### Task 1: Org-wide + category-filtered `match_findings`

The only infra change. Extend the `match_findings` contract so `kb_id` may be `None` (search all KBs in the store's org) and an optional `categories` filter narrows by `category`. This is what makes `scope='both'` possible. Existing single-KB callers are unaffected (additive, defaulted args).

**Files:**
- Modify: `backend/brain2/store/base.py:25-33` (protocol signature + docstring)
- Modify: `backend/brain2/store/sqlite.py:170-212` (`match_findings` impl)
- Modify: `backend/brain2/store/supabase.py:72-92` (`match_findings` impl)
- Create: `supabase/migrations/0008_match_findings_org.sql`
- Test: `backend/tests/test_match_findings_global.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_match_findings_global.py`:

```python
"""Local-tier test for org-wide + category-filtered match_findings.

kb_id=None searches every KB in the org; `categories` narrows by category.
Vectors are nonzero only in dimension 0, so all are parallel (cosine
similarity 1.0) — membership is deterministic regardless of magnitude.
"""
from __future__ import annotations

from brain2.store.sqlite import SQLiteStore

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_match_findings_global.py -v`
Expected: FAIL — `match_findings()` does not accept `None` for `kb_id` / the `categories` kwarg (TypeError or wrong results).

- [ ] **Step 3: Update the Store protocol**

In `backend/brain2/store/base.py`, replace the `match_findings` protocol method (lines 25-33) with:

```python
    async def match_findings(
        self,
        kb_id: str | None,
        query_embedding: list[float],
        match_count: int,
        min_similarity: float,
        categories: list[str] | None = None,
    ) -> list[dict]:
        """Vector-search findings; rows carry a `similarity` field.

        `kb_id` scopes to one KB; `kb_id=None` searches every KB in the store's
        org (the load-bearing org filter — SQLite's synthetic ``"local"`` or the
        SupabaseStore's injected ``org_id``). `categories`, when given, restricts
        results to those `category` values.
        """
        ...
```

- [ ] **Step 4: Implement the SQLite impl**

In `backend/brain2/store/sqlite.py`, replace `match_findings` (lines 170-212) with:

```python
    async def match_findings(
        self,
        kb_id: str | None,
        query_embedding: list[float],
        match_count: int,
        min_similarity: float,
        categories: list[str] | None = None,
    ) -> list[dict]:
        """Cosine KNN over vec_findings joined to findings; rows carry `similarity`.

        `kb_id=None` searches every KB in the local org; `categories` filters by
        `category`. Mirrors the Postgres ``match_findings`` RPC return shape:
        ``id, title, content, category, confidence, tags, provenance, similarity``
        ordered by descending similarity (= 1 - cosine distance), dropping rows
        below ``min_similarity``. JSON columns are decoded."""
        q = serialize_float32(query_embedding)
        select_cols = ", ".join(f"f.{c}" for c in _FINDING_MATCH_COLS)
        where: list[str] = []
        params: list[object] = [q]
        if kb_id is not None:
            where.append("f.kb_id = ?")
            params.append(kb_id)
        else:
            where.append("f.org_id = ?")
            params.append(_ORG)
        if categories:
            placeholders = ",".join("?" for _ in categories)
            where.append(f"f.category IN ({placeholders})")
            params.extend(categories)
        params.append(match_count)
        rows = self._conn.execute(
            f"""
            SELECT {select_cols},
                   vec_distance_cosine(v.embedding, ?) AS dist
            FROM vec_findings v JOIN findings f ON f.id = v.finding_id
            WHERE {' AND '.join(where)}
            ORDER BY dist LIMIT ?;
            """,
            params,
        ).fetchall()
        out: list[dict] = []
        for r in rows:
            similarity = 1.0 - float(r["dist"])
            if similarity < min_similarity:
                continue
            out.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "content": r["content"],
                    "category": r["category"],
                    "confidence": r["confidence"],
                    "tags": _json_load(r["tags"], []),
                    "provenance": _json_load(r["provenance"], []),
                    "similarity": similarity,
                }
            )
        return out
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_match_findings_global.py -v`
Expected: PASS (2 assertions).

- [ ] **Step 6: Update the Supabase impl + write the migration**

In `backend/brain2/store/supabase.py`, replace `match_findings` (lines 72-92) with:

```python
    async def match_findings(
        self,
        kb_id: str | None,
        query_embedding: list[float],
        match_count: int,
        min_similarity: float,
        categories: list[str] | None = None,
    ) -> list[dict]:
        """Mirrors agent/preamble.py select_preamble — the match_findings RPC.

        Runs against the service client (the preamble path already uses a service
        client for this read). `kb_id=None` searches the whole org via the
        explicit ``match_org_id`` filter (the tenancy invariant — never run
        org-wide without it); `categories` narrows by category. Rows carry a
        `similarity` field."""
        args: dict = {
            "query_embedding": query_embedding,
            "match_kb_id": kb_id,
            "match_count": match_count,
            "min_similarity": min_similarity,
        }
        if kb_id is None:
            args["match_org_id"] = self._resolve_org()
        if categories:
            args["match_categories"] = list(categories)
        res = service_client().rpc("match_findings", args).execute()
        return res.data or []
```

Create `supabase/migrations/0008_match_findings_org.sql`:

```sql
-- -----------------------------------------------------------------------------
-- 0008: match_findings — org-wide + category-filtered search
-- Extends the 0001 RPC so kb_id may be null (search the whole org, scoped by
-- match_org_id) and an optional match_categories array filters by category.
-- Powers the journal's scope='both' recall across the journal + every KB's notes.
-- The arg list changes, so the old function is dropped first (create-or-replace
-- cannot alter a signature).
-- -----------------------------------------------------------------------------

drop function if exists match_findings(vector, uuid, int, real);

create or replace function match_findings(
  query_embedding  vector(1536),
  match_kb_id      uuid default null,
  match_count      int default 10,
  min_similarity   real default 0.0,
  match_org_id     uuid default null,
  match_categories text[] default null
)
returns table (
  id           uuid,
  title        text,
  content      text,
  category     text,
  confidence   real,
  tags         text[],
  provenance   jsonb,
  similarity   real
)
language sql stable
as $$
  select
    f.id, f.title, f.content, f.category, f.confidence, f.tags, f.provenance,
    1 - (f.embedding <=> query_embedding) as similarity
  from findings f
  where (match_kb_id is null or f.kb_id = match_kb_id)
    and (match_org_id is null or f.org_id = match_org_id)
    and (match_categories is null or f.category = any(match_categories))
    and f.embedding is not null
    and 1 - (f.embedding <=> query_embedding) >= min_similarity
  order by f.embedding <=> query_embedding
  limit match_count;
$$;
```

- [ ] **Step 7: Verify nothing else broke + commit**

Run: `pytest tests/ -q -k "match_findings or preamble or note"`
Expected: PASS (existing single-KB callers still pass `kb_id` positionally; new args default).

```bash
git add backend/brain2/store/base.py backend/brain2/store/sqlite.py backend/brain2/store/supabase.py supabase/migrations/0008_match_findings_org.sql backend/tests/test_match_findings_global.py
git commit -m "feat(store): org-wide + category-filtered match_findings (kb_id=None)"
```

---

### Task 2: Reserved journal scope + `persist_journal`

The journal's storage primitive: a reserved scope constant and a near-clone of `persist_note` that writes a `category="journal"` finding plus a markdown mirror in the **global** `~/.brain2/journal/` dir — and never schedules a synopsis rebuild.

**Files:**
- Create: `backend/brain2/constants.py`
- Create: `backend/brain2/livingdocs/journal.py`
- Test: `backend/tests/test_journal_tool.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_journal_tool.py`:

```python
"""Local-tier test for persist_journal: a `journal` Finding + a global markdown
file, with NO synopsis rebuild. Mirrors test_note_tool.py's harness — real
SQLiteStore via tmp BRAIN2_DB_PATH, only the embedder faked.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DIM = 1536


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


async def test_persist_journal_writes_finding_and_global_md(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))

    import brain2.livingdocs.journal as journal_mod
    import brain2.store as store_pkg
    from brain2.constants import JOURNAL_SCOPE
    from brain2.interfaces.mcp.tenancy import resolve_tenant

    store_pkg._local_stores.clear()
    monkeypatch.setattr(journal_mod, "embed_batch", _fake_embed_batch)

    ctx = resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=True)
    res = await journal_mod.persist_journal(
        ctx, text="learned that X composes cleanly", type="insight", tags=["arch"]
    )

    assert res["finding_id"]
    assert res["entry_path"].endswith(".md")
    # markdown mirror lives in the GLOBAL journal dir (tmp BRAIN2_DB_PATH parent)
    assert Path(res["entry_path"]).parent == tmp_path / "journal"
    assert Path(res["entry_path"]).exists()

    store = store_pkg.get_store(ctx.access_token)
    got = store.get_finding(ctx.kb_id, res["finding_id"])
    assert got["category"] == "journal"
    assert "journal" in got["tags"] and "insight" in got["tags"] and "arch" in got["tags"]

    store_pkg._local_stores.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_journal_tool.py -v`
Expected: FAIL — `No module named 'brain2.constants'` / `brain2.livingdocs.journal`.

- [ ] **Step 3: Create the scope constant**

Create `backend/brain2/constants.py`:

```python
"""Cross-cutting constants shared by the store and feature layers.

Kept dependency-free so low-level modules (e.g. store/sqlite.py) can import it
without a cycle through the feature packages that also use it.
"""
from __future__ import annotations

# Reserved, repo-independent tenancy scope for the cross-project journal. Used as
# both the project and KB name; resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE)
# yields a stable, org-scoped journal KB that is never derived from a repo+branch.
JOURNAL_SCOPE = "__journal__"
```

- [ ] **Step 4: Implement `persist_journal`**

Create `backend/brain2/livingdocs/journal.py`:

```python
"""Persist a journal entry as a `journal` Finding AND a global markdown file.

A journal entry is the cross-project, write-anytime counterpart to a session
note. Unlike persist_note it (1) stores under the reserved JOURNAL_SCOPE KB,
(2) writes its markdown to the GLOBAL ~/.brain2/journal/ dir (not a project's
.brain2/), and (3) never schedules a synopsis rebuild — the journal is not tied
to any repo+branch.

    persist_journal(ctx, text, type?, tags?) ──► finding{category:'journal'} + md
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from brain2.agent.state import TenantContext
from brain2.clients.embeddings import embed_batch
from brain2.constants import JOURNAL_SCOPE  # noqa: F401 — re-exported for callers
from brain2.store import get_store


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "entry"


def journal_dir() -> Path:
    """Global journal markdown dir: ``<brain2 home>/journal``, created on demand.

    Colocated with the SQLite db so the journal travels with the store — the
    parent of ``BRAIN2_DB_PATH`` when set, else ``~/.brain2``."""
    env = os.environ.get("BRAIN2_DB_PATH")
    root = Path(env).resolve().parent if env else Path.home() / ".brain2"
    d = root / "journal"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _entry_filename(captured_at: str, title: str) -> str:
    """ISO-8601 captured_at + title → ``2026-06-03-1430-slug.md``."""
    return f"{captured_at[:10]}-{captured_at[11:16].replace(':', '')}-{_slug(title)}.md"


def _markdown(title: str, text: str, type_: str, tags: list[str]) -> str:
    """On-disk entry body: an H1 title, an optional meta line, then the text."""
    meta: list[str] = []
    if type_:
        meta.append(f"type: {type_}")
    if tags:
        meta.append(f"tags: {', '.join(tags)}")
    head = f"# {title}\n"
    if meta:
        head += "\n" + " · ".join(meta) + "\n"
    return f"{head}\n{text.strip()}\n"


async def persist_journal(
    ctx: TenantContext,
    *,
    text: str,
    type: str = "",
    tags: list[str] | None = None,
    title: str = "",
    originating_project: str = "",
    session_id: str = "",
    captured_at: str = "",
) -> dict:
    """Embed + insert the entry as a `journal` Finding, then write the markdown.

    Returns ``{"finding_id", "entry_path"}``. `type` (e.g. insight/reflection/
    reference/decision) and `tags` are folded into the finding's tags for
    filtering. `originating_project`, when given, is stamped into provenance —
    where you were when you journaled — but storage is always the journal scope.
    """
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()
    tags = list(tags or [])
    title = title.strip()
    if not title:
        first = text.strip().splitlines()[0] if text.strip() else ""
        title = first[:80] or "entry"

    all_tags = ["journal", *([type] if type else []), *tags]
    prov: dict = {"source": "brain2-journal", "session": session_id}
    if originating_project:
        prov["project"] = originating_project

    row = {
        "org_id": ctx.org_id,
        "kb_id": ctx.kb_id,
        "title": title[:120],
        "content": text,
        "category": "journal",
        "confidence": 1.0,
        "tags": all_tags,
        "provenance": [prov],
    }
    [embedding] = await embed_batch([text])
    row["embedding"] = embedding
    [finding_id] = await get_store(ctx.access_token).insert_findings([row])

    entry_path = journal_dir() / _entry_filename(captured_at, title)
    entry_path.write_text(_markdown(title, text, type, tags))
    return {"finding_id": finding_id, "entry_path": str(entry_path)}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_journal_tool.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/brain2/constants.py backend/brain2/livingdocs/journal.py backend/tests/test_journal_tool.py
git commit -m "feat(journal): persist_journal + reserved __journal__ scope"
```

---

### Task 3: `brain2_journal` write MCP tool

Expose journaling as an MCP tool the agent can call **any time**. Thin wrapper: resolve the reserved journal tenant, call `persist_journal`.

**Files:**
- Modify: `backend/brain2/interfaces/mcp/server.py` (add import + `_journal_impl` + `brain2_journal` after `brain2_distill`, around line 170)
- Test: `backend/tests/test_journal_tool.py` (add a tool-level case)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_journal_tool.py`:

```python
async def test_brain2_journal_tool_writes_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))

    import brain2.livingdocs.journal as journal_mod
    import brain2.store as store_pkg
    from brain2.interfaces.mcp import server

    store_pkg._local_stores.clear()
    monkeypatch.setattr(journal_mod, "embed_batch", _fake_embed_batch)

    res = await server._journal_impl(
        text="prefer scope filters over separate corpora", type="decision"
    )

    assert res["finding_id"]
    assert res["scope"] == "journal"
    assert res["entry_path"].endswith(".md")

    store_pkg._local_stores.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_journal_tool.py::test_brain2_journal_tool_writes_entry -v`
Expected: FAIL — `server` has no attribute `_journal_impl`.

- [ ] **Step 3: Implement the tool**

In `backend/brain2/interfaces/mcp/server.py`, add to the imports near line 36-38:

```python
from brain2.livingdocs.journal import persist_journal
from brain2.constants import JOURNAL_SCOPE
```

Then insert, immediately after the `brain2_distill` tool (after line 169):

```python
async def _journal_impl(
    text, type="", tags=None, title="", project="", project_path="", session_id=""
):
    ctx = resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=True)
    res = await persist_journal(
        ctx,
        text=text,
        type=type,
        tags=tags or [],
        title=title,
        originating_project=project,
        session_id=session_id,
    )
    return {**res, "scope": "journal"}


@mcp.tool()
async def brain2_journal(
    text: str,
    type: str = "",
    tags: list[str] | None = None,
    title: str = "",
    project: str = "",
    project_path: str = "",
    session_id: str = "",
) -> dict:
    """Write a personal JOURNAL entry — cross-project, searchable any time.

    Unlike brain2_note (a session note bound to the current repo+branch, written
    at session end), the journal is your global notebook: call this WHENEVER
    something is worth keeping — an insight, a decision, a reflection, a pointer.
    `type` is a free label (insight | reflection | reference | decision) and
    `tags` add filterable keywords; both feed search. `title` is optional (the
    first line is used if omitted). `project`/`project_path` are optional context
    (where you were) stamped into provenance — storage is always the journal
    scope. Returns {finding_id, entry_path, scope}."""
    return await _journal_impl(text, type, tags, title, project, project_path, session_id)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_journal_tool.py -v`
Expected: PASS (all cases in the file).

- [ ] **Step 5: Commit**

```bash
git add backend/brain2/interfaces/mcp/server.py backend/tests/test_journal_tool.py
git commit -m "feat(journal): brain2_journal MCP write tool"
```

---

### Task 4: `brain2_journal_search` + `brain2_journal_recent` MCP tools

The dedicated recall surface. `search` maps `scope` to a `match_findings` call (`journal` / `project` / `both`); `recent` is a thin chronological list.

**Files:**
- Modify: `backend/brain2/interfaces/mcp/server.py` (add `_journal_search_impl` + two tools after `brain2_journal`)
- Test: `backend/tests/test_journal_search.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_journal_search.py`:

```python
"""Local-tier test for brain2_journal_search scope filters. Seeds findings
directly (journal entry in the __journal__ KB, a note in a project KB) and
asserts each scope returns the right corpus. embed_text is faked at its source
module so the search path makes no OpenAI call.
"""
from __future__ import annotations

import hashlib

DIM = 1536


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_text(text: str) -> list[float]:
    return _fake_vec(text)


async def test_journal_search_scopes(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setattr("brain2.clients.embeddings.embed_text", _fake_embed_text)

    import brain2.store as store_pkg
    from brain2.constants import JOURNAL_SCOPE
    from brain2.interfaces.mcp import server
    from brain2.interfaces.mcp.tenancy import resolve_tenant

    store_pkg._local_stores.clear()
    jctx = resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=True)
    pctx = resolve_tenant("proj", "main", create=True)
    store = store_pkg.get_store()
    await store.insert_findings(
        [
            {"kb_id": jctx.kb_id, "title": "j-entry", "content": "alpha insight",
             "category": "journal", "tags": ["journal", "insight"],
             "embedding": _fake_vec("alpha insight")},
            {"kb_id": pctx.kb_id, "title": "p-note", "content": "beta note",
             "category": "note", "tags": ["note"],
             "embedding": _fake_vec("beta note")},
        ]
    )

    j = await server._journal_search_impl("alpha", scope="journal")
    assert {r["title"] for r in j["results"]} == {"j-entry"}

    p = await server._journal_search_impl("beta", scope="project", project="proj", kb="main")
    assert {r["title"] for r in p["results"]} == {"p-note"}

    b = await server._journal_search_impl("alpha", scope="both")
    assert {r["title"] for r in b["results"]} == {"j-entry", "p-note"}

    # type filter narrows journal results
    none = await server._journal_search_impl("alpha", scope="journal", type="reflection")
    assert none["results"] == []

    store_pkg._local_stores.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_journal_search.py -v`
Expected: FAIL — `server` has no attribute `_journal_search_impl`.

- [ ] **Step 3: Implement the search + recent tools**

In `backend/brain2/interfaces/mcp/server.py`, insert after the `brain2_journal` tool (from Task 3):

```python
async def _journal_search_impl(
    query, scope="both", type=None, limit=10, project="", kb="", project_path=""
):
    from brain2.clients.embeddings import embed_text

    emb = await embed_text(query)
    min_sim = 0.0
    if scope == "journal":
        ctx = resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=True)
        store = get_store(ctx.access_token, org_id=ctx.org_id)
        rows = await store.match_findings(ctx.kb_id, emb, limit, min_sim, categories=["journal"])
    elif scope == "project":
        ctx = resolve_tenant(project, kb, create=False)
        store = get_store(ctx.access_token, org_id=ctx.org_id)
        rows = await store.match_findings(ctx.kb_id, emb, limit, min_sim, categories=["note"])
    else:  # "both" — org-wide across the journal + every KB's notes
        store = resolve_store()
        rows = await store.match_findings(None, emb, limit, min_sim, categories=["journal", "note"])

    results: list[dict] = []
    for r in rows:
        tags = r.get("tags") or []
        if type and type not in tags:
            continue
        results.append(
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "snippet": (r.get("content") or "")[:240],
                "score": round(float(r.get("similarity") or 0.0), 4),
                "category": r.get("category"),
                "tags": tags,
            }
        )
    return {"results": results, "scope": scope, "count": len(results)}


@mcp.tool()
async def brain2_journal_search(
    query: str,
    scope: str = "both",
    type: str | None = None,
    limit: int = 10,
    project: str = "",
    kb: str = "",
    project_path: str = "",
) -> dict:
    """Search your journal (and optionally your project notes) by meaning.

    `scope` selects the corpus: ``journal`` (your cross-project entries only),
    ``project`` (this repo+branch's session notes only — pass project/kb), or
    ``both`` (default — journal entries + every project's notes in one ranked
    list). `type` further filters journal results by label (insight/reflection/
    …). Returns {results: [{title, snippet, score, category, tags, id}], scope,
    count}, ranked by similarity."""
    return await _journal_search_impl(query, scope, type, limit, project, kb, project_path)


@mcp.tool()
async def brain2_journal_recent(limit: int = 10) -> dict:
    """List your most recent journal entries, newest first (no query).

    Returns {entries: [{id, title, category, confidence, tags, created_at}],
    count}. Use to skim what you've journaled lately; use brain2_journal_search
    to find by meaning."""
    ctx = resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=True)
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    res = store.list_findings(ctx.kb_id, category="journal", limit=limit)
    return {"entries": res.get("findings", []), "count": res.get("count", 0)}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_journal_search.py -v`
Expected: PASS (4 assertions).

- [ ] **Step 5: Commit**

```bash
git add backend/brain2/interfaces/mcp/server.py backend/tests/test_journal_search.py
git commit -m "feat(journal): brain2_journal_search + brain2_journal_recent tools"
```

---

### Task 5: Hide the `__journal__` scope from project listings

The journal write creates a `__journal__` project/KB. It must not appear in `brain2_projects` (which powers the `/brain2:pickup` selector). Filter the sentinel in both `list_projects` impls. (Note: it never enters the activity graph — that's fed only by `brain2_capture`, which the journal does not call.)

**Files:**
- Modify: `backend/brain2/store/sqlite.py:453-478` (`list_projects`)
- Modify: `backend/brain2/store/supabase.py:252-...` (`list_projects` project query)
- Test: `backend/tests/test_journal_search.py` (add a case)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_journal_search.py`:

```python
async def test_list_projects_hides_journal_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))

    import brain2.store as store_pkg
    from brain2.constants import JOURNAL_SCOPE
    from brain2.interfaces.mcp.tenancy import resolve_tenant

    store_pkg._local_stores.clear()
    resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=True)
    resolve_tenant("realproj", "main", create=True)

    names = {p["project"] for p in store_pkg.get_store().list_projects()}
    assert "realproj" in names
    assert JOURNAL_SCOPE not in names

    store_pkg._local_stores.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_journal_search.py::test_list_projects_hides_journal_scope -v`
Expected: FAIL — `__journal__` is present in the project names.

- [ ] **Step 3: Filter the sentinel in SQLite `list_projects`**

In `backend/brain2/store/sqlite.py`, add the import near the top (after line 42, the `_ORG` definition):

```python
from brain2.constants import JOURNAL_SCOPE
```

Then in `list_projects` (line 456-458), change the projects query to exclude the sentinel:

```python
        prows = self._conn.execute(
            "SELECT id, name FROM projects WHERE org_id = ? AND name != ? ORDER BY created_at;",
            (_ORG, JOURNAL_SCOPE),
        ).fetchall()
```

- [ ] **Step 4: Filter the sentinel in Supabase `list_projects`**

In `backend/brain2/store/supabase.py`, add the import near the other top-level imports:

```python
from brain2.constants import JOURNAL_SCOPE
```

Then in `list_projects`, change the projects query (the `sb.table("projects")...` call) to add a `.neq`:

```python
        prows = (
            sb.table("projects").select("id, name")
            .eq("org_id", org_id).neq("name", JOURNAL_SCOPE)
            .order("created_at").execute()
        ).data or []
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_journal_search.py -v`
Expected: PASS (all cases, including the new one).

- [ ] **Step 6: Commit**

```bash
git add backend/brain2/store/sqlite.py backend/brain2/store/supabase.py backend/tests/test_journal_search.py
git commit -m "feat(journal): hide __journal__ scope from project listings"
```

---

### Task 6: `/brain2:journal` skill + plugin registration

The user-facing surface. A skill with three modes (write / search / recent) and registration in the plugin manifest. No automated test — verify manually by listing the skill.

**Files:**
- Create: `skills/journal/SKILL.md`
- Modify: `.claude-plugin/plugin.json` (add `./skills/journal` to `skills`)

- [ ] **Step 1: Write the skill**

Create `skills/journal/SKILL.md`:

```markdown
---
name: journal
description: Your cross-project personal journal — write an entry any time (insight, reflection, reference, decision) and search it back by meaning. Distinct from session notes (which are per repo+branch, written at session end); the journal is global and on-demand. Use when the user wants to jot a durable thought, "journal this", "note to self", or recall past entries ("what did I conclude about X", "search my journal").
---

# brain2 — Journal (cross-project, write-anytime, searchable)

The journal is your **global notebook**, separate from session notes. Session
notes are bound to the current repo+branch and written automatically at session
end; a journal entry is written **whenever you choose** and is **searchable
across every project**. Both live in the same `~/.brain2/brain.db`; the journal
just uses a reserved, repo-independent scope.

## Step 0 — Resolve optional context

The journal itself is global, so a write needs no project. But it's useful to
stamp **where you were** when you journaled, and `scope=project|both` searches
need the current repo+branch:

```bash
basename "$(git rev-parse --show-toplevel)"   # project (optional context)
git branch --show-current                     # kb
git rev-parse --show-toplevel                 # project_path
```

If not in a git repo, omit them (writes still work; `scope=project` is then N/A).

## Mode select — branch on the args

| Invocation | Mode | Do |
|---|---|---|
| `/brain2:journal <text>` | **Write** | Step A — save an entry |
| `/brain2:journal search <query> [--scope both\|journal\|project] [--type T]` | **Search** | Step B — recall by meaning |
| `/brain2:journal recent [N]` | **Recent** | Step C — list latest entries |

If the first arg is `search` or `recent`, use that mode; otherwise treat the
whole input as the text to journal.

## Step A — Write an entry

From the user's text, infer a `type` (one of `insight`, `reflection`,
`reference`, `decision`) and any obvious `tags`; when unclear, leave `type`
empty. Then call:

`mcp__plugin_brain2_brain2__brain2_journal(text, type, tags, title, project, project_path)`

- `text` — the entry (required).
- `type` / `tags` — your inferred label + keywords (optional).
- `project` / `project_path` — the resolved repo context, if any (optional).

On success it returns `{finding_id, entry_path, scope}`. Confirm briefly: echo
the one-line title and the `type`, e.g. *"Journaled (decision): prefer scope
filters over separate corpora."* Do not paste the whole entry back.

## Step B — Search the journal

Parse `--scope` (default `both`) and optional `--type` from the args; the rest
is the query. Call:

`mcp__plugin_brain2_brain2__brain2_journal_search(query, scope, type, limit, project, kb, project_path)`

- `scope=journal` — your journal entries only.
- `scope=project` — this repo+branch's session notes only (pass `project`/`kb`).
- `scope=both` (default) — journal entries **and** every project's notes.

It returns `{results: [{title, snippet, score, category, tags, id}], scope,
count}`, ranked by similarity. Render the top results as a short list — title,
a one-line snippet, and the `category` (journal vs note) so the user can tell
their notebook from their work-logs. If `count` is 0, say so and suggest a
broader `--scope` or different wording.

## Step C — List recent entries

`/brain2:journal recent [N]` (default 10). Call
`mcp__plugin_brain2_brain2__brain2_journal_recent(limit=N)`. It returns
`{entries: [{title, tags, created_at, ...}], count}`. Render newest-first as a
compact list (date · title · type). This is a chronological skim, not a search.
```

- [ ] **Step 2: Register the skill in the plugin manifest**

In `.claude-plugin/plugin.json`, add `"./skills/journal"` to the `skills` array (after `"./skills/docs"`):

```json
  "skills": [
    "./skills/pickup",
    "./skills/capture",
    "./skills/search",
    "./skills/explore",
    "./skills/activity",
    "./skills/schema",
    "./skills/notes",
    "./skills/docs",
    "./skills/journal"
  ],
```

- [ ] **Step 3: Verify the manifest parses**

Run (from repo root `/Users/suherli/Repositories/brain2`):
`python -c "import json; json.load(open('.claude-plugin/plugin.json')); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add skills/journal/SKILL.md .claude-plugin/plugin.json
git commit -m "feat(journal): /brain2:journal skill + plugin registration"
```

---

### Final verification

- [ ] **Run the full suite + lint**

From `backend/`:
```bash
pytest -q
ruff check . && ruff format --check .
```
Expected: all tests PASS; ruff clean. If `pyright` is part of the repo's gate, run it too and resolve any new errors in the touched files.

- [ ] **Manual smoke (optional)**

Reload the brain2 plugin in Claude Code, then in any repo:
`/brain2:journal noticed the journal reuses the findings table cleanly`
`/brain2:journal search journal --scope journal`
Confirm the entry is written (a file appears under `~/.brain2/journal/`) and search returns it.

---

## Self-Review (completed during authoring)

**Spec coverage:**
- Reserved `__journal__` scope → Task 2 (constants) + used in Tasks 3–5. ✓
- `persist_journal` (clone of `persist_note`, global md, no rebuild) → Task 2. ✓
- `brain2_journal` write tool (any-time) → Task 3. ✓
- `brain2_journal_search` (journal/project/both) + `brain2_journal_recent` → Task 4. ✓
- Org-wide + category `match_findings` across SQLite + Supabase + migration 0008 → Task 1. ✓
- Hide `__journal__` from project/activity/pickup → Task 5 (list_projects, both tiers; activity is capture-only so untouched — noted). ✓
- `/brain2:journal` skill + registration → Task 6. ✓
- Free-text + optional `type`/`tags`, one finding embedded whole → Task 2/3. ✓
- Tests for write, search scopes, org-wide match, sentinel hiding → Tasks 1–5. ✓

**Placeholder scan:** No TBD/TODO; every code + test step is complete. `brain2_journal_recent` dropped the inert `days` param (no date filter exists) to avoid a configured-but-inert knob.

**Type consistency:** `match_findings(kb_id: str | None, …, categories=None)` is identical across base/sqlite/supabase and all call sites. `persist_journal` returns `{finding_id, entry_path}`; `_journal_impl` adds `scope`; tests assert exactly those keys. `JOURNAL_SCOPE` is defined once in `brain2/constants.py` and imported everywhere (no duplicated literal, no import cycle).

**Out of scope (per spec):** no distilled docs tree for the journal, no local embeddings, no per-section schema, no proactive hook, no forced local-only tier.
