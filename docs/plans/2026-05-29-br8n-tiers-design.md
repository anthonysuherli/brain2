# br8n — Free (local) + Paid (cloud) tiers

**Date:** 2026-05-29
**Status:** Design approved; implementation pending.

## Goal

Ship br8n in two tiers from one engine:

- **Free / public** — a fully local cache. Data lives on-device (SQLite +
  `sqlite-vec`). User brings their own `OPENAI_API_KEY` (embeddings) and
  `TAVILY_API_KEY` (explore). No account, no Supabase, single device.
- **Paid / cloud** — today's Supabase backend deployed as a managed multi-tenant
  service. Adds managed keys, cross-machine sync, cross-repo search, and teams.

The split is **storage and identity**, not logic. All engine code is shared.

## Architecture

```
                 ┌─────────────────────────────────────┐
                 │      shared engine (pure logic)       │
                 │  capture · preamble · synopsis ·      │
                 │  exploration · adapter · Finding shape │
                 └──────────────────┬────────────────────┘
                                    │ Store protocol
                  ┌─────────────────┴──────────────────┐
                  ▼                                     ▼
        ┌───────────────────┐               ┌────────────────────┐
        │  FREE — local      │               │  PAID — cloud       │
        │  SQLiteStore       │               │  SupabaseStore      │
        │  ~/.br8n/db      │               │  (today's backend)  │
        │  BYO keys          │               │  managed keys       │
        │  no auth, 1 device │               │  GoTrue + RLS       │
        │  current repo only │               │  sync · cross-repo  │
        └───────────────────┘               │  · teams            │
                                            └────────────────────┘
```

The engine never imports a storage client directly. It calls `store = get_store()`;
the `BR8N_BACKEND=local|cloud` env var (or absence of cloud creds) picks the impl.

## The Store protocol

`br8n/store/base.py` — the full surface the 11 Supabase-coupled files need:

```python
class Store(Protocol):
    # findings — the hot path
    async def match_findings(self, kb_id, query_embedding,
                             match_count, min_similarity) -> list[dict]: ...
    async def insert_findings(self, rows: list[dict]) -> list[str]: ...
    def get_finding(self, kb_id, finding_id) -> dict: ...
    def list_findings(self, kb_id, category=None, limit=None) -> list[dict]: ...
    def delete_finding(self, kb_id, finding_id) -> None: ...

    # synopsis spine
    def load_synopsis(self, kb_id) -> dict | None: ...
    def upsert_synopsis(self, kb_id, content, finding_count) -> None: ...

    # exploration row lifecycle
    def create_exploration(self, kb_id, prompt) -> str: ...
    def update_exploration(self, id, **patch) -> None: ...
    def get_exploration(self, id) -> dict | None: ...

    # tenancy — find-or-create by name
    def resolve_project(self, name, create) -> str: ...
    def resolve_kb(self, project_id, name, create) -> str: ...

    # monitoring — no-op locally
    async def record_access(self, **kw) -> None: ...
```

Two implementations:

- **`SupabaseStore`** — wraps today's `service_client()` / `user_client()` calls
  verbatim (the `match_findings` RPC, `findings` inserts, GoTrue tenancy). A move
  of existing code behind the interface; no behavior change.
- **`SQLiteStore`** — SQLite + `sqlite-vec`. `match_findings` → `vec0` cosine query;
  `insert_findings` → INSERT with embedding as a vec blob; synopsis one row per KB;
  single synthetic `org_id="local"`, no RLS.

`get_store()` reads `BR8N_BACKEND` (or infers from creds) and returns a cached
singleton.

## Free (local) specifics

### Schema (SQLite)

```sql
CREATE TABLE findings (
  id TEXT PRIMARY KEY, kb_id TEXT NOT NULL,
  title TEXT, content TEXT, category TEXT,
  confidence REAL, tags TEXT, provenance TEXT,   -- tags/provenance = JSON
  created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE vec_findings USING vec0(finding_id TEXT, embedding float[1536]);
CREATE TABLE projects     (id TEXT PRIMARY KEY, name, created_at);
CREATE TABLE kbs          (id TEXT PRIMARY KEY, project_id, name, created_at);
CREATE TABLE kb_synopsis  (kb_id TEXT PRIMARY KEY, content, finding_count, built_at);
CREATE TABLE explorations (id TEXT PRIMARY KEY, kb_id, prompt, status, finding_ids, ...);
```

`match_findings`:
```sql
SELECT f.*, 1 - vec_distance_cosine(v.embedding, ?) AS similarity
FROM vec_findings v JOIN findings f ON f.id = v.finding_id
WHERE f.kb_id = ? ORDER BY similarity DESC LIMIT ?;
```

- **Location:** `~/.br8n/brain.db` (override `BR8N_DB_PATH`). `~/.br8n/config.toml`
  holds BYO keys so they aren't env-only.
- **Tenancy:** no GoTrue/JWT/RLS. `resolve_tenant` is a pure SQLite find-or-create;
  `org_id="local"`, `access_token` unused. `TenantContext` keeps its shape.
- **Entry points:**
  - MCP server — in-process against `SQLiteStore`, no port. Plugin `.mcp.json` sets
    `BR8N_BACKEND=local`.
  - VS Code extension — free tier spawns a `uvicorn` bound to `127.0.0.1` against the
    same DB; `require_api_key` is bypassed when `BR8N_BACKEND=local`.
- **Migrations:** `_ensure_schema()` runs `CREATE TABLE IF NOT EXISTS` on first open.

## Paid (cloud) specifics + value props

Cloud MVP = today's backend behind `SupabaseStore` + a real auth surface. The four
props layer on, cheapest-first:

1. **Managed keys** *(ships with MVP)* — cloud ignores user keys and uses br8n's
   server-side keys, metered per subscription. Already how the deployed backend runs.
2. **Cross-machine sync** *(the reason to pay)* — **thin sync for v1**: device runs
   `BR8N_BACKEND=cloud` with the user's API key; every read/write hits Supabase
   directly. No local DB, no merge, online-only but trivial. Offline thick-sync
   (local SQLite + background push/pull) is a later upgrade.
3. **Cross-repo /search** — org-wide `match_findings_across_kbs(org_id, qvec)` RPC +
   a `/br8n:search` mode that omits the repo filter. One RPC + one skill flag.
4. **Team sharing** *(last)* — schema already carries `org_id` + RLS on org
   membership; teams = invites + member management on existing tenancy.

**Identity:** Supabase GoTrue (today's email/password login, real "Sign in with
br8n" later). The API key the extension already sends becomes the cloud token.

## Config + selection

```python
def get_store() -> Store:
    backend = os.getenv("BR8N_BACKEND")
    if not backend:
        backend = "cloud" if _has_cloud_creds() else "local"
    return {"local": SQLiteStore, "cloud": SupabaseStore}[backend]()  # cached
```

`Settings` splits: infra creds (Supabase, server keys) become **optional** so the
local tier boots with neither.

## The refactor

Eleven files call `service_client()` directly. Each → `store = get_store()` + a
protocol method:

| Today | Becomes |
|---|---|
| `service_client().rpc("match_findings", …)` | `store.match_findings(…)` |
| `user_client(tok).table("findings").insert(rows)` | `store.insert_findings(rows)` |
| `load_synopsis(client, kb_id)` | `store.load_synopsis(kb_id)` |
| `resolve_tenant` GoTrue login | `store.resolve_project/kb` |
| `record_access(...)` | `store.record_access(...)` (no-op local) |

Pure logic — `band_findings`, `assess_coverage`, the snapshot→Finding adapter, the
whole `exploration/` pipeline — **does not change**.

Coupled files: `agent/preamble.py`, `agent/synopsis.py`, `api/explore.py`,
`api/resume.py`, `capture/service.py`, `clients/supabase.py`, `findings/ingest.py`,
`findings/service.py`, `interfaces/mcp/server.py`, `interfaces/mcp/tenancy.py`,
`monitoring/recorder.py`.

## Packaging

- **Free:** `pip install br8n` (or bundled binary) → `~/.br8n/`, BYO keys,
  `/plugin install`. `sqlite-vec` is a pip wheel (no system deps).
- **Paid:** hosted service (current backend) + a "sign in" flow in extension/plugin.

## Build sequence

1. Extract `Store` protocol; move existing Supabase calls into `SupabaseStore`
   (no behavior change — cloud still works). **Lowest risk; verify against current
   cloud path before SQLite exists.**
2. Write `SQLiteStore` + `_ensure_schema` + `sqlite-vec` wiring.
3. Flip the 11 call sites to `get_store()`; add `BR8N_BACKEND` + creds inference.
4. Bundle the localhost uvicorn / in-process MCP for the free tier.
5. Layer paid features: managed keys (free) → thin sync → cross-repo search → teams.

## Out of scope (YAGNI for v1)

- Offline thick-sync with conflict resolution (thin sync first).
- Team invites / member management UI (schema supports it; build last).
- "Sign in with br8n" OAuth (reuse email/password login for now).
