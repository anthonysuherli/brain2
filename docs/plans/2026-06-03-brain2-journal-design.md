# brain2 journal — cross-project, write-anytime, semantically searchable

**Date:** 2026-06-03
**Status:** Design approved, pending implementation plan
**Author:** Anthony Suherli (with Claude)

## Summary

Add a **journal** to brain2: a cross-project, personal note corpus you can write
to at any time and search semantically. It is distinct from brain2's existing
repo+branch *session notes* but lives in the same store and reuses the same
embeddings and vector search. Inspired by `private-journal-mcp`, rehosted on
brain2's infrastructure.

This is a **scoping + surface** feature, not new storage. brain2's local store
is already a single user-home database (`~/.brain2/brain.db`,
`backend/brain2/store/sqlite.py:107-114`) shared across every project; the
per-project `.brain2/` folder only holds notes markdown, the docs tree, and
policy JSON. A "user-global journal" is therefore a reserved, repo-independent
*scope* over findings that already exist, plus write/search surfaces over it.

## Motivation

brain2 already has multi-section notes (configurable policy), embeddings (OpenAI
`text-embedding-3-small`, 1536-dim), and vector search (`match_findings`). What
it lacks, relative to `private-journal-mcp`:

1. A **user-global** corpus — notes are strictly repo+branch scoped today.
2. A **dedicated note-search** surface — notes are buried in unified findings
   search with no first-class "search my notes" entry point.
3. **Any-time** journaling — notes are written only at session end via the Stop
   hook (`hooks/session-note.py`).

Three deltas chosen in brainstorming. Explicitly **not** chosen: local/offline
embeddings (keep OpenAI), per-section entry schema (free-text + type), proactive
journaling prompts.

## Decisions (from brainstorming)

- **Boundary:** separate journal corpus + unified search. You write to the
  journal explicitly; search takes a `scope` filter (`journal | project | both`).
- **Entry shape:** free-text body + optional `type` and `tags`. One finding per
  entry, embedded whole.
- **Embeddings:** reuse brain2's existing OpenAI stack. No local embeddings.
- **Storage tier:** journal follows brain2's existing backend selection (local
  SQLite by default, cloud Supabase if configured). Not forced local-only.
- **Markdown mirror:** on, at a global path, for portability/grep.

## Architecture

A journal entry is a brain2 finding under a **reserved, repo-independent scope**,
sharing all existing infrastructure.

```
brain2_journal(text, type?, tags?)
   └─ embed_batch([text])  (OpenAI 1536)
   └─ insert finding { category:'journal', kb_id: JOURNAL_KB }  ──► ~/.brain2/brain.db
   └─ write markdown                                            ──► ~/.brain2/journal/<date>-<slug>.md

brain2_journal_search(query, scope='both', type?, limit=10)
   └─ embed query
   └─ match_findings(...) with scope→(org_id, kb_id, categories) mapping
   └─ ranked entries
```

**Reused unchanged:** `embed_batch` (`backend/brain2/clients/embeddings.py`), the
global `~/.brain2/brain.db`, finding storage, sqlite-vec / pgvector vector search.

**Net-new:** one write path, one search path, a reserved scope, a skill, and one
store capability (org-wide search — see "Infra change").

### The journal scope

Reserve the project/kb name **`__journal__`**. Tenancy in brain2 is resolved by
name, create-on-demand
(`backend/brain2/interfaces/mcp/tenancy.py:101-136`):
`resolve_tenant("__journal__", "__journal__", create=True)` yields a stable
`kb_id`, per-org. Org is per-user, so the journal is **cross-project by
construction** — never derived from any repo+branch.

**Org vs. user scope.** The journal is scoped to `org_id`, matching all existing
finding tenancy. In the local tier (this user's case) `org_id="local"` is a
single user, so the journal is effectively personal. In a cloud org with
multiple members the journal would be **org-shared**, not per-person; truly
personal journals in shared orgs (add a `user_id` predicate) are a future
refinement, out of scope for v1.

The reserved scope **must be hidden** from work-oriented listings:
`brain2_projects`, `/brain2:activity`, and the `/brain2:pickup` cross-repo
selector filter out the `__journal__` sentinel so it never pollutes resume/work
views.

### Write — `brain2_journal` (MCP tool) + `persist_journal` (livingdocs)

A near-clone of `persist_note` (`backend/brain2/livingdocs/notes.py:38-81`):

- Tool: `brain2_journal(text, type?, tags?, title?)`.
  - `type` ∈ {`insight`, `reflection`, `reference`, `decision`} — a free string,
    not enforced; default empty/`note`.
  - `title` optional; auto-derived from the first line / a slug when omitted.
- `persist_journal(ctx, text, type, tags, title)`:
  - Resolve the journal tenant (`__journal__`/`__journal__`, create=True).
  - Row: `category="journal"`, `tags=["journal", type, *tags]`,
    `confidence=1.0`, `provenance=[{source:"brain2-journal", session, ...}]`.
    The tool may optionally accept the originating `project`/`project_path`
    (where you were when you journaled) and stamp it into provenance — handy
    context, but storage is always the journal scope.
  - `embed_batch([text])` → `embedding`; `insert_findings([row])`.
  - Write markdown to `~/.brain2/journal/YYYY-MM-DD-HHMM-slug.md` (global path,
    sibling to `brain.db`), **not** in any project's `.brain2/`.
  - **No `schedule_rebuild`** — synopsis is a repo+branch concept, irrelevant
    here.

A new global path helper is required (the existing `DocPaths` in
`backend/brain2/livingdocs/paths.py` is project-scoped); add a journal-dir
resolver rooted at `Path.home() / ".brain2" / "journal"`, honoring
`BRAIN2_DB_PATH`'s parent if set, to stay colocated with the db.

### Search — `brain2_journal_search(query, scope='both', type?, limit=10)`

Maps `scope` to a vector-search call:

| scope | query |
|---|---|
| `journal` | `match_findings(kb_id=JOURNAL_KB, categories=['journal'])` |
| `project` | `match_findings(kb_id=<current repo+branch kb>, categories=['note'])` |
| `both` (default) | org-wide `match_findings(org_id, kb_id=None, categories=['journal','note'])` |

Like sibling tools, `brain2_journal_search` takes the standard
`(project, kb, project_path)` tenancy args; `scope='project'` and `scope='both'`
resolve the current repo+branch kb from them (the skill derives them from git, as
the other skills do). `scope='journal'` ignores them. `scope='both'` returns
journal entries **and** every project's notes (cross-repo) in one ranked list.
Optional `type` further filters journal results by tag.

Results: `{title, snippet, score, type, scope, path, captured_at}`. Snippet is a
content excerpt; ranking is cosine similarity (descending), limited to `limit`.

### Recent — `brain2_journal_recent(limit=10, days=30)` (optional, include if cheap)

Thin chronological list of recent journal entries (title, type, captured_at,
path) for "what did I journal lately", independent of semantic search. Backed by
`list_findings(JOURNAL_KB, category="journal")` ordered by recency.

## Infra change — org-wide vector search

Today `match_findings` is single-`kb_id` (`backend/brain2/store/base.py:25-33`,
the cloud RPC in `supabase/migrations/0001_init.sql:350-377`). `scope='both'`
needs cross-kb search within an org. **Extend `match_findings`** to accept:

- optional `kb_id=None` → search all kbs in `org_id`;
- optional `categories: list[str] | None = None` → filter by category.

Implementations:

- **SQLite** (`backend/brain2/store/sqlite.py`): add `org_id` and
  `category IN (...)` predicates to the existing `vec_findings` join. When
  `kb_id` is provided, keep the current behavior; when `None`, drop the kb
  predicate and scope by `org_id` (`"local"`). Trivial.
- **Cloud / Supabase**: new migration replacing the `match_findings` RPC to take
  `match_org_id`, a nullable `match_kb_id`, and `match_categories text[]`.
  Existing callers pass `kb_id` + `categories=null` → behavior unchanged. Update
  `SupabaseStore.match_findings` accordingly.

`scope='journal'` and `scope='project'` use the single-kb path (with a
`categories` filter); only `scope='both'` uses `kb_id=None`.

**Low-risk alternative** (rejected): add a separate `match_findings_global`
method and leave `match_findings` untouched — more duplication, zero risk to
existing flows. Chosen approach extends the one method; existing callers are
updated in the same change.

## Surfaces

### MCP tools (`backend/brain2/interfaces/mcp/server.py`)

Tools self-register alongside `brain2_note` / `brain2_distill`:

- `brain2_journal(text, type?, tags?, title?)`
- `brain2_journal_search(query, scope?, type?, limit?)`
- `brain2_journal_recent(limit?, days?)` (optional)

### Skill — `/brain2:journal` (`skills/journal/SKILL.md`)

- `/brain2:journal <text>` — write (agent infers `type`/`tags` or passes
  through).
- `/brain2:journal search <q> [--scope both|journal|project] [--type T]` —
  ranked recall.
- `/brain2:journal recent [--days N]` — recent entries.

Register the skill in `.claude-plugin/plugin.json`'s `skills` list.

### Any-time journaling

The MCP tool is callable by the agent **whenever** something worth recording
happens — an insight, a decision, a reflection — not gated to the session-end
Stop hook. The user also writes explicitly via the skill. No proactive
journaling hook in v1.

## Out of scope (v1)

- No distilled `.brain2/docs` tree for the journal (search-first; revisit if
  entries accumulate).
- No local/offline embeddings (kept OpenAI).
- No per-section entry schema (free-text + type).
- No proactive journaling prompt/hook.
- No forced local-only privacy tier (journal follows the active backend).

## Testing

Mirror `backend/tests/test_note_tool.py` with a `tmp` `BRAIN2_DB_PATH`:

- `test_journal_tool.py` — `brain2_journal` writes a `category='journal'`
  finding with the right tags/provenance, writes the global markdown file, and
  does **not** trigger a synopsis rebuild.
- `test_journal_search.py` — the three scope filters; `scope='both'` returns
  journal entries + cross-kb notes (seed findings under two distinct project
  kbs + the journal kb); `type` filter narrows journal results.
- Extend `backend/tests/test_store_selection.py` or add a store test for the
  org-wide `match_findings(kb_id=None, categories=[...])` path on SQLite.

## Files touched (anticipated)

| File | Change |
|---|---|
| `backend/brain2/livingdocs/journal.py` (new) | `persist_journal`, journal-dir path helper |
| `backend/brain2/interfaces/mcp/server.py` | register `brain2_journal*` tools |
| `backend/brain2/store/base.py` | `match_findings` signature: optional `kb_id`, `categories` |
| `backend/brain2/store/sqlite.py` | org-wide + category-filtered query |
| `backend/brain2/store/supabase.py` | call updated RPC |
| `supabase/migrations/0008_match_findings_org.sql` (new) | replace `match_findings` RPC |
| `backend/brain2/interfaces/mcp/server.py` / projects/activity/pickup paths | hide `__journal__` sentinel |
| `skills/journal/SKILL.md` (new) | `/brain2:journal` skill |
| `.claude-plugin/plugin.json` | register skill |
| `backend/tests/test_journal_tool.py`, `test_journal_search.py` (new) | coverage |

## Open defaults (flag if wrong)

- Journal follows brain2's existing backend (local by default, cloud if
  configured). OpenAI embeddings either way.
- Markdown mirror on (portability) rather than DB-only.
- `brain2_journal_recent` included if it stays a thin list; drop if it bloats
  the surface.
