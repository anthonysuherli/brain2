# br8n journal — cross-project, write-anytime, semantically searchable

**Date:** 2026-06-03
**Status:** Design approved, pending implementation plan
**Author:** Anthony Suherli (with Claude)

## Summary

Add a **journal** to br8n: a cross-project, personal note corpus you can write
to at any time and search semantically. It is distinct from br8n's existing
repo+branch *session notes* but lives in the same store and reuses the same
embeddings and vector search. Inspired by `private-journal-mcp`, rehosted on
br8n's infrastructure.

This is a **scoping + surface** feature, not new storage. br8n's local store
is already a single user-home database (`~/.br8n/brain.db`,
`backend/br8n/store/sqlite.py:107-114`) shared across every project; the
per-project `.br8n/` folder only holds notes markdown, the docs tree, and
policy JSON. A "user-global journal" is therefore a reserved, repo-independent
*scope* over findings that already exist, plus write/search surfaces over it.

## Motivation

br8n already has multi-section notes (configurable policy), embeddings (OpenAI
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
- **Embeddings:** reuse br8n's existing OpenAI stack. No local embeddings.
- **Storage tier:** journal follows br8n's existing backend selection (local
  SQLite by default, cloud Supabase if configured). Not forced local-only.
- **Markdown mirror:** on, at a global path, for portability/grep.

## Architecture

A journal entry is a br8n finding under a **reserved, repo-independent scope**,
sharing all existing infrastructure.

```
br8n_journal(text, type?, tags?)
   └─ embed_batch([text])  (OpenAI 1536)
   └─ insert finding { category:'journal', kb_id: JOURNAL_KB }  ──► ~/.br8n/brain.db
   └─ write markdown                                            ──► ~/.br8n/journal/<date>-<slug>.md

br8n_journal_search(query, scope='both', type?, limit=10)
   └─ embed query
   └─ match_findings(...) with scope→(org_id, kb_id, categories) mapping
   └─ ranked entries
```

**Reused unchanged:** `embed_batch` (`backend/br8n/clients/embeddings.py`), the
global `~/.br8n/brain.db`, finding storage, sqlite-vec / pgvector vector search.

**Net-new:** one write path, one search path, a reserved scope, a skill, and one
store capability (org-wide search — see "Infra change").

### The journal scope

Reserve the project/kb name **`__journal__`**. Tenancy in br8n is resolved by
name, create-on-demand
(`backend/br8n/interfaces/mcp/tenancy.py:101-136`):
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
`br8n_projects`, `/br8n:activity`, and the `/br8n:pickup` cross-repo
selector filter out the `__journal__` sentinel so it never pollutes resume/work
views.

### Write — `br8n_journal` (MCP tool) + `persist_journal` (livingdocs)

A near-clone of `persist_note` (`backend/br8n/livingdocs/notes.py:38-81`):

- Tool: `br8n_journal(text, type?, tags?, title?)`.
  - `type` ∈ {`insight`, `reflection`, `reference`, `decision`} — a free string,
    not enforced; default empty/`note`.
  - `title` optional; auto-derived from the first line / a slug when omitted.
- `persist_journal(ctx, text, type, tags, title)`:
  - Resolve the journal tenant (`__journal__`/`__journal__`, create=True).
  - Row: `category="journal"`, `tags=["journal", type, *tags]`,
    `confidence=1.0`, `provenance=[{source:"br8n-journal", session, ...}]`.
    The tool may optionally accept the originating `project`/`project_path`
    (where you were when you journaled) and stamp it into provenance — handy
    context, but storage is always the journal scope.
  - `embed_batch([text])` → `embedding`; `insert_findings([row])`.
  - Write markdown to `~/.br8n/journal/YYYY-MM-DD-HHMM-slug.md` (global path,
    sibling to `brain.db`), **not** in any project's `.br8n/`.
  - **No `schedule_rebuild`** — synopsis is a repo+branch concept, irrelevant
    here.

A new global path helper is required (the existing `DocPaths` in
`backend/br8n/livingdocs/paths.py` is project-scoped); add a journal-dir
resolver rooted at `Path.home() / ".br8n" / "journal"`, honoring
`BR8N_DB_PATH`'s parent if set, to stay colocated with the db.

### Search — `br8n_journal_search(query, scope='both', type?, limit=10)`

Maps `scope` to a vector-search call:

| scope | query |
|---|---|
| `journal` | `match_findings(kb_id=JOURNAL_KB, categories=['journal'])` |
| `project` | `match_findings(kb_id=<current repo+branch kb>, categories=['note'])` |
| `both` (default) | org-wide `match_findings(org_id, kb_id=None, categories=['journal','note'])` |

Like sibling tools, `br8n_journal_search` takes the standard
`(project, kb, project_path)` tenancy args; `scope='project'` and `scope='both'`
resolve the current repo+branch kb from them (the skill derives them from git, as
the other skills do). `scope='journal'` ignores them. `scope='both'` returns
journal entries **and** every project's notes (cross-repo) in one ranked list.
Optional `type` further filters journal results by tag.

Results: `{title, snippet, score, type, scope, path, captured_at}`. Snippet is a
content excerpt; ranking is cosine similarity (descending), limited to `limit`.

### Recent — `br8n_journal_recent(limit=10, days=30)` (optional, include if cheap)

Thin chronological list of recent journal entries (title, type, captured_at,
path) for "what did I journal lately", independent of semantic search. Backed by
`list_findings(JOURNAL_KB, category="journal")` ordered by recency.

## Infra change — org-wide vector search

Today `match_findings` is single-`kb_id` (`backend/br8n/store/base.py:25-33`,
the cloud RPC in `supabase/migrations/0001_init.sql:350-377`). `scope='both'`
needs cross-kb search within an org. **Extend `match_findings`** to accept:

- optional `kb_id=None` → search all kbs in `org_id`;
- optional `categories: list[str] | None = None` → filter by category.

Implementations:

- **SQLite** (`backend/br8n/store/sqlite.py`): add `org_id` and
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

### MCP tools (`backend/br8n/interfaces/mcp/server.py`)

Tools self-register alongside `br8n_note` / `br8n_distill`:

- `br8n_journal(text, type?, tags?, title?)`
- `br8n_journal_search(query, scope?, type?, limit?)`
- `br8n_journal_recent(limit?, days?)` (optional)

### Skill — `/br8n:journal` (`skills/journal/SKILL.md`)

- `/br8n:journal <text>` — write (agent infers `type`/`tags` or passes
  through).
- `/br8n:journal search <q> [--scope both|journal|project] [--type T]` —
  ranked recall.
- `/br8n:journal recent [--days N]` — recent entries.

Register the skill in `.claude-plugin/plugin.json`'s `skills` list.

### Any-time journaling

The MCP tool is callable by the agent **whenever** something worth recording
happens — an insight, a decision, a reflection — not gated to the session-end
Stop hook. The user also writes explicitly via the skill. No proactive
journaling hook in v1.

## Out of scope (v1)

- No distilled `.br8n/docs` tree for the journal (search-first; revisit if
  entries accumulate).
- No local/offline embeddings (kept OpenAI).
- No per-section entry schema (free-text + type).
- No proactive journaling prompt/hook.
- No forced local-only privacy tier (journal follows the active backend).

## Testing

Mirror `backend/tests/test_note_tool.py` with a `tmp` `BR8N_DB_PATH`:

- `test_journal_tool.py` — `br8n_journal` writes a `category='journal'`
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
| `backend/br8n/livingdocs/journal.py` (new) | `persist_journal`, journal-dir path helper |
| `backend/br8n/interfaces/mcp/server.py` | register `br8n_journal*` tools |
| `backend/br8n/store/base.py` | `match_findings` signature: optional `kb_id`, `categories` |
| `backend/br8n/store/sqlite.py` | org-wide + category-filtered query |
| `backend/br8n/store/supabase.py` | call updated RPC |
| `supabase/migrations/0008_match_findings_org.sql` (new) | replace `match_findings` RPC |
| `backend/br8n/interfaces/mcp/server.py` / projects/activity/pickup paths | hide `__journal__` sentinel |
| `skills/journal/SKILL.md` (new) | `/br8n:journal` skill |
| `.claude-plugin/plugin.json` | register skill |
| `backend/tests/test_journal_tool.py`, `test_journal_search.py` (new) | coverage |

## Open defaults (flag if wrong)

- Journal follows br8n's existing backend (local by default, cloud if
  configured). OpenAI embeddings either way.
- Markdown mirror on (portability) rather than DB-only.
- `br8n_journal_recent` included if it stays a thin list; drop if it bloats
  the surface.
