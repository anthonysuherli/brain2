# Activity Knowledge Graph — design

**Date:** 2026-05-30
**Status:** Approved design (pre-implementation)
**Target:** First open beta — final feature

## Summary

Every br8n user gets a default **activity knowledge graph**: a per-user, cross-repo
graph (entities + edges) that accumulates automatically as a side effect of workspace
captures. It tracks what the user is working on — repos touched, branches, files
edited, and the intent (Task) behind each work session — and is queryable via an MCP
tool, surfaced in the resume card, and exposed over a small REST API.

Unlike the delapan KG (where users co-design an ontology and run an explicit
extraction over a KB's findings), the activity KG has a **known, seeded ontology** and
**populates incrementally on every capture** with zero extra user action.

## Decisions (from brainstorming)

1. **Shape:** a true knowledge graph (nodes + edges), not just a timeline KB.
2. **Tiers:** both — local SQLite (free beta) and cloud Supabase, via the `Store` protocol.
3. **Population:** auto-extract on every capture (deterministic structural pass +
   gated LLM pass over the hypothesis).
4. **Surfaces:** `br8n_activity` MCP tool + cross-repo resume card + `/v1/activity`
   REST endpoints. VS Code activity view deferred (post-beta).

## 1. Tenancy & namespace

The activity KG is per-user = **per `org_id`** (local tier: singleton `org_id="local"`;
cloud: the JWT-derived org). It deliberately breaks the normal `project=repo /
kb=branch` convention because it spans all repos.

**Reserved namespace** — a sentinel project+kb per org:

```
project: __activity__     kb: default     ->  activity_kb_id
```

New helper:

```python
resolve_activity_kb(org_id) -> activity_kb_id   # find-or-create, reuses store.resolve_project/resolve_kb
```

**Grounding without duplication.** A capture still writes its snapshot Finding into the
*home* repo+branch KB (unchanged — the resume loop depends on it). The activity KG is a
**separate graph namespace**: `kg_nodes.kb_id = activity_kb_id`. Nodes carry
`grounded_in = [snapshot_finding_id]` (an opaque reference back to the home-KB finding).
Findings are **not duplicated**; the activity KB is purely a graph container. Repo/branch
context also rides along as node/edge *properties* so the graph is self-describing.

## 2. Storage layer (Store protocol + both backends)

New graph surface on the `Store` protocol (`store/base.py`):

```python
upsert_kg_nodes(kb_id, nodes) -> dict[label, node_id]   # embeds + dedupes, merges props/grounded_in
upsert_kg_edges(kb_id, edges) -> int                    # resolves endpoints, drops dangling/self/dupe
match_kg_node(kb_id, embedding, threshold) -> dict|None # dedupe probe (internal to upsert)
get_kg_subgraph(kb_id, *, seed_embedding=None, labels=None, limit) -> {nodes, edges}
kg_stats(kb_id) -> {node_count, edge_count, by_type, hotspots}
clear_kg(kb_id) -> None                                  # rebuild path (unused by activity append)
```

**SQLiteStore** — new DDL, mirroring the existing findings/`vec0` pattern:

```sql
CREATE TABLE IF NOT EXISTS kg_nodes (
  id TEXT PRIMARY KEY, org_id TEXT, kb_id TEXT NOT NULL,
  label TEXT, type TEXT, properties TEXT, grounded_in TEXT, created_at TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS vec_kg_nodes USING vec0(node_id TEXT, embedding float[1536]);
CREATE TABLE IF NOT EXISTS kg_edges (
  id TEXT PRIMARY KEY, org_id TEXT, kb_id TEXT NOT NULL,
  source_id TEXT, target_id TEXT, relation TEXT, properties TEXT, grounded_in TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_kb ON kg_nodes(kb_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_kb ON kg_edges(kb_id);
```

Node dedupe reuses the proven `vec0` cosine search: embed the node label, search
`vec_kg_nodes` within `kb_id`, reuse the existing node id above threshold (merge
`properties` + `grounded_in`), else insert.

**SupabaseStore** — reuses delapan's **existing** `kg_nodes`/`kg_edges` tables and the
`match_kg_nodes` RPC (same instance, same schema — zero migration divergence). Methods
are thin wrappers.

All engine code stays backend-agnostic (`get_store()` only).

## 3. Activity ontology + extraction

**Seeded ontology** — a fixed `activity_schema` (`KGSchema`) for the activity KB. No
propose/approve flow (YAGNI for beta).

```
Node types:
  Repo     props: name, path
  Branch   props: name
  File     props: path, repo
  Session  props: captured_at, trigger, hypothesis
  Task     props: summary            (LLM-derived intent)

Relations (validity-constrained):
  Session --on_repo-->   Repo
  Session --on_branch--> Branch
  Branch  --in_repo-->   Repo
  Session --edited-->    File          (cursor_file + diff files)
  Session --viewed-->    File          (other open_files)
  File    --in_repo-->   Repo
  Session --pursued-->   Task          (from hypothesis)
  Task    --in_repo-->   Repo
```

**Two-pass extraction** — `activity_extract(snapshot, finding_id) -> KGExtraction`:

1. **Deterministic pass** (pure Python over snapshot fields). Builds Repo/Branch/File/
   Session nodes + all structural edges. No LLM, no failure modes. Repo/Branch/File are
   **stable dedupe targets** — every capture in `br8n/dev` resolves to the *same* Repo
   and Branch nodes, so the graph compounds instead of fragmenting.
2. **LLM pass (gated)** — the ported delapan `extractor` over just the `hypothesis`
   → **Task** nodes + `pursued`/`in_repo` edges. Soft-regime extractor never raises
   (empty on failure). Gated by `BR8N_ACTIVITY_LLM` (default on).

Both passes merge into one `KGExtraction`; every node `grounded_in=[snapshot_finding_id]`.
`Session` nodes are unique per capture (timestamp); Repo/Branch/File/Task compound.

## 4. Population flow

New module `backend/br8n/knowledge_graph/activity.py`:

```python
def schedule_activity_update(home_ctx, snapshot, finding_id) -> None
    # fire-and-forget; never blocks or breaks capture
```

Runs **after** `persist_snapshot` returns, in the background:

1. `activity_kb_id = resolve_activity_kb(home_ctx.org_id)`
2. `extraction = activity_extract(snapshot, finding_id)`
3. `store.upsert_kg_nodes(activity_kb_id, extraction.nodes)` → label→id map
4. `store.upsert_kg_edges(activity_kb_id, resolved_edges)`

**Two call sites** (both already do fire-and-forget synopsis rebuilds):
- `api/capture.py` — after `persist_snapshot`.
- `interfaces/mcp/server.py::br8n_capture` — after persist.

Best-effort: wrapped in try/except, logged, never propagated. **A KG failure must never
fail a capture.**

## 5. Surfaces

**`br8n_activity` MCP tool** (`server.py`) — params `query`, optional `repo`/`since`.
Embeds the query, `get_kg_subgraph(activity_kb_id, seed_embedding=…)`, returns
`{nodes, edges, summary}` (short NL rollup). Mirrors `delapan_graph`.

**Cross-repo resume card** (`api/resume.py`) — resume additionally resolves
`activity_kb_id`, pulls recent `Session` nodes grouped by Repo/Branch, and the card
renderer gains an **"Activity"** section (`br8n/dev · 2h ago`, `delapan/main ·
yesterday`). Purely additive to the existing card HTML.

**REST API** (`api/activity.py`, new router):
- `GET /v1/activity/graph?q=&repo=&since=` → subgraph JSON
- `GET /v1/activity/stats` → `kg_stats` (hotspots: most-touched repos/files, counts)

Both use `require_api_key` (no-op on local) and resolve the activity KB for the org.

## 6. Error handling, config, testing

**Error handling (cardinal rule: never break capture).**
- `schedule_activity_update` fully wrapped — any exception caught, logged WARNING,
  swallowed. Capture latency/success unaffected.
- LLM pass: delapan extractor guarantee — failure → empty extraction, never raises.
  Structural nodes still land.
- Embedding failure during dedupe → skip the vec probe, insert fresh (degrades to
  no-dedupe, not data loss).
- `upsert_kg_edges` drops dangling endpoints, self-loops, duplicates (ported) — malformed
  extractions can't corrupt the graph.
- Reserved-KB resolve is idempotent find-or-create; concurrent captures rely on the same
  find-or-create the tenancy layer already handles.

**Config.**
- `BR8N_ACTIVITY_KG=1` (default on) — master switch; off = capture behaves as today.
- `BR8N_ACTIVITY_LLM=1` (default on) — gates only the hypothesis→Task LLM pass;
  off = deterministic-only (free, instant).
- `BR8N_KG_DEDUPE_THRESHOLD` (default ~0.92) — node-merge cosine threshold.

**Testing.**
- *Store unit (SQLite, real sqlite-vec):* node insert + dedupe-merge, edge endpoint
  resolution / dangling-drop, subgraph query, `kg_stats`.
- *Extraction unit:* deterministic pass over a fixture snapshot → exact expected
  nodes/edges; same repo+branch twice → dedupes to one Repo/Branch.
- *Flow:* `schedule_activity_update` with a throwing stubbed store/LLM → never raises.
- *Surfaces:* `br8n_activity` returns a subgraph; resume card includes Activity
  section; API endpoints return expected JSON shapes.
- *Supabase:* thin wrappers over delapan's proven tables/RPC — shared Store contract
  test (SQLite in CI; Supabase behind an integration marker).

## 7. Porting summary

Copy `delapan/knowledge_graph/{models,schema,extractor}.py` → `br8n/knowledge_graph/`
(rename `delapan.*` → `br8n.*`). Adapt `builder.py` persistence to call **Store
protocol** methods instead of direct Supabase RPC (tier-agnostic).

New br8n code:
- `knowledge_graph/activity.py` — `schedule_activity_update` + two-pass `activity_extract`
- `knowledge_graph/activity_schema.py` — seeded ontology
- `store/base.py` graph methods + `SQLiteStore`/`SupabaseStore` implementations
- `interfaces/mcp/server.py::br8n_activity` tool
- `api/activity.py` router + resume-card rollup in `api/resume.py`
- `resolve_activity_kb` helper (tenancy)

## Out of scope (beta)

- VS Code activity graph visualization (post-beta).
- User-editable / proposable activity ontology (it's seeded and fixed).
- Community detection, advanced KG analytics beyond simple hotspots.
- Rebuild/backfill of historical snapshots into the graph (forward-only on capture;
  `clear_kg` exists but no batch backfill tool for beta).
