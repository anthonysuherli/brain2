# brain2

Context-capture and resume engine — eliminates the 9.5-minute context-rebuild tax by
capturing developer intent on interruption and replaying it as a 30-second resume card.

## Architecture

brain2 is a self-contained fork of the Divergence engine. The core engine files
(config, clients, agent/preamble, agent/synopsis, findings, kbs, projects, monitoring)
are copied from `../divergence/backend/divergence/` with all imports renamed from
`divergence.*` to `brain2.*`. Do NOT add a cross-repo import dependency — keep
brain2 fully standalone.

### What's new (brain2-specific)

- `brain2/capture/` — WorkspaceSnapshot model, snapshot→Finding adapter, persist service
- `brain2/knowledge_graph/` — the **activity KG**: per-user, cross-repo work graph
  (`models.py` = node/edge carriers ported from divergence; `activity.py` = seeded
  ontology + deterministic-plus-gated-LLM extraction, fire-and-forget population on
  capture, and the query/rollup/stats read surfaces)
- `brain2/api/` — FastAPI: `/v1/capture`, `/v1/resume/{project}/{kb}`, `/v1/explore/...`,
  `/v1/activity/{graph,stats}`
- `brain2/interfaces/mcp/server.py` — MCP tools: `brain2_capture`, `brain2_resume`,
  `brain2_explore`, `brain2_activity`
- `vscode-extension/` — VS Code extension (capture triggers + resume card webview)
- `ios-app/` — native SwiftUI companion (first standalone UI). v1 = read spine:
  Sign in, browse cross-repo activity, read resume cards. Consumes `/v1/projects`
  + `/v1/resume?format=json` + `/v1/activity/stats`. XcodeGen project (`project.yml`,
  no checked-in `.xcodeproj`). Design: `docs/plans/2026-05-30-ios-companion-design.md`
- `skills/` — Claude Code plugin skills (built; see Plugin section below)
- `.claude-plugin/` — plugin manifest + local dev marketplace; root `.mcp.json` wires the brain2 MCP server

### What's reused from the fork

- `config`, `clients/*`, `agent/preamble`, `agent/synopsis`, `agent/state` — preamble + coverage banding
- `findings/*`, `kbs/*`, `projects/*` — KB CRUD + finding persistence
- `exploration/*` — the gap-fill pipeline (plan→search→crawl→extract→merge)
- `monitoring/recorder.py` — access recording (only `recorder.py`, not the full module)
- `interfaces/mcp/tenancy.py` — name→tenant resolution

### What's excluded from the fork (not needed)

- `agent/graph.py` — LangGraph chat agent
- `api/agent.py`, `api/public.py`, `api/internal.py` — chat + deploy surfaces
- `research/` — HTML report generation
- `knowledge_graph/` (generic KG) — the divergence build_graph/propose_schema/extractor
  machinery (user-curated ontology over all findings) stays excluded. brain2's
  `knowledge_graph/` ports only `models.py` and adds its own **activity** graph; the
  generic finding→graph builder is not needed by the capture/resume loop.
- `monitoring/service.py`, `monitoring/report.py` — only `recorder.py` is copied

## Storage tiers

brain2 ships in two tiers from one engine. The split is **storage + identity**;
all engine logic (capture, preamble/coverage, synopsis, exploration) is shared and
never touches a storage client directly — it calls `store = get_store()`.

- **`brain2/store/`** — `Store` protocol (`base.py`) with two implementations:
  - `SQLiteStore` (free/local) — SQLite + `sqlite-vec`, single synthetic
    `org_id="local"`, no auth/no Supabase/single device. DB at `~/.brain2/brain.db`
    (override `BRAIN2_DB_PATH`); `_ensure_schema()` runs `CREATE TABLE IF NOT EXISTS`
    on first open. Cached as a per-`db_path` singleton (one reused connection).
  - `SupabaseStore` (paid/cloud) — wraps today's `service_client()` / `user_client()`
    calls (GoTrue + pgvector + RLS). Built fresh per request (carries the per-request
    `access_token` for RLS scope).
  - The protocol also carries the **activity-graph** surface (`upsert_kg_nodes`,
    `upsert_kg_edges`, `match_kg_nodes`, `get_kg_subgraph`, `list_kg_nodes`,
    `kg_stats`). SQLite adds `kg_nodes`/`vec_kg_nodes`/`kg_edges` tables; Supabase
    reuses divergence's existing `kg_nodes`/`kg_edges` + `match_kg_nodes` RPC. Node
    dedupe is exact `(kb_id, type, label)`; stored label embeddings power only
    semantic subgraph seeding, never dedupe.
- **Selection** — `active_backend()` / `get_store()` read `BRAIN2_BACKEND`
  (`"local"` | `"cloud"`); if unset, cloud iff Supabase creds present, else local.
  `active_backend()` is importable from `brain2.store`.
- **Tenancy fork** — `resolve_tenant` (mcp/tenancy.py) forks on `active_backend()`:
  local skips GoTrue (`user_id="local"`, `access_token=""`, `org_id="local"`); cloud
  does the GoTrue login for a real JWT. `TenantContext` shape is identical on both.
- **Auth fork** — `api/auth.py::require_api_key` is a no-op on the local tier
  (loopback-only, single user — no `BRAIN2_API_KEY` needed) and validates the Bearer
  key exactly as before on cloud. Safe only because the local server binds 127.0.0.1.
- **Settings** — Supabase/server creds are **optional**, so the local tier boots with
  none. `service_client()` raises clearly only if the cloud path is hit creds-less.

**Cloud value props (FUTURE — not built).** Cloud MVP today = the Supabase backend
behind `SupabaseStore` + the existing GoTrue login. The paid differentiators —
(1) managed keys, (2) cross-machine sync, (3) cross-repo search, (4) team sharing —
are designed (see `docs/plans/2026-05-29-brain2-tiers-design.md`) but not yet
implemented. Do not document them as shipping.

## Setup

`uv` is the intended toolchain, but it may not be installed — the venv reality is
plain `python3.11 -m venv`. The local tier additionally needs `sqlite-vec`.

```bash
cd backend
python3.11 -m venv .venv          # or: uv venv
.venv/bin/pip install -e ".[dev]" sqlite-vec   # or: uv sync && uv pip install sqlite-vec
cp .env.example .env              # pick the FREE or PAID block (see file)
```

**Free / local tier** (SQLite, no Supabase, no API key, loopback-only):

```bash
BRAIN2_BACKEND=local python -m brain2.api.main   # blessed launcher: enforces loopback (auth is off)
BRAIN2_BACKEND=local python -m brain2.interfaces.mcp.server
```

**Paid / cloud tier** (today's Supabase backend; needs the cloud .env block):

```bash
uvicorn brain2.api.main:app --reload --port 8002
python -m brain2.interfaces.mcp.server          # add to .claude/settings.json
```

```bash
# Install VS Code extension dependencies
cd vscode-extension
npm install
npm run build
# Then press F5 in VS Code to launch the Extension Development Host
```

## Conventions

- Imports: always `from brain2.*` — never `from divergence.*`
- Engine updates: when syncing engine improvements from divergence, apply them manually
  (copy file, rename imports). Do NOT re-introduce a cross-repo dep.
- Auth: cloud tier uses a pre-shared API key (`BRAIN2_API_KEY` in .env = `brain2.apiKey`
  in VS Code secrets); local tier requires no key (loopback-only, see Storage tiers)
- Supabase (cloud tier): same instance and schema as divergence (no migration divergence)
- KB naming: project = workspace folder name, kb = git branch name

## Phase status

- [x] Phase 0 — Engine fork (Supabase, pgvector, Finding, preamble/tap)
- [x] Phase 1 — VS Code extension scaffold (triggers, capture, resume card)
- [x] Phase 2 — Resume card polish (hypothesis prominent, snapshot count, auto-resume on focus)
- [x] Phase 3 — Always-open explore seam (gap-band → explore pipeline → auto-refresh card)
- [x] Storage tiers — `Store` protocol + `SQLiteStore`/`SupabaseStore`, `get_store()`/
  `active_backend()` selection, free-tier local entry points (no-auth loopback API +
  local MCP). Paid value props (sync/cross-repo/managed-keys/teams) remain future.
- [x] Activity KG — per-user, cross-repo work graph that auto-populates on every
  capture (deterministic structural pass + gated LLM task distillation), on both
  tiers via the `Store` graph surface. Surfaces: `brain2_activity` MCP tool,
  cross-repo rollup on the resume card, `/v1/activity/{graph,stats}`. Best-effort:
  a graph failure never breaks a capture. Gates: `BRAIN2_ACTIVITY_KG` (master,
  default on), `BRAIN2_ACTIVITY_LLM` (task pass, default on — off = deterministic
  only). Design: `docs/plans/2026-05-30-activity-kg-design.md`.

## API surface

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Health check |
| `/v1/capture` | POST | Save a workspace snapshot as a Finding |
| `/v1/resume/{project}/{kb}` | GET | Tap KB → resume card. `?format=html` (default, webview) or `?format=json` (native, structured: hypothesis/snapshots/synopsis/activity/coverage/preamble) |
| `/v1/projects` | GET | Discovery: caller's repos+branches with last-activity + snapshot-count chips (the iOS home screen; `Store.list_projects`) |
| `/v1/explore/{project}/{kb}` | POST | Start gap-fill pipeline (returns exploration_id) |
| `/v1/explore/{id}/status` | GET | Poll exploration progress + results |
| `/v1/activity/graph` | GET | Query the cross-repo activity graph (semantic `q`, optional `repo`) |
| `/v1/activity/stats` | GET | Activity-graph totals + hotspots (most-touched repos/files/tasks) |

## MCP tools (for Claude Code)

| Tool | Purpose |
|---|---|
| `brain2_capture` | Persist a workspace snapshot |
| `brain2_resume` | Tap KB → resume card (preamble + coverage) |
| `brain2_explore` | Run gap-fill pipeline synchronously (blocks ~1-3 min) |
| `brain2_activity` | Query the cross-repo activity graph (subgraph + NL summary) |

## Plugin (Claude Code skills)

brain2 ships as a Claude Code plugin alongside the VS Code extension. Skills live
in `skills/` and follow the Divergence pattern — Markdown files that direct how
Claude Code behaves for each slash command, calling the `brain2_*` MCP tools.

```
skills/
  _shared/preamble-first.md   shared grounding convention (calls brain2_resume)
  resume/SKILL.md             /brain2:resume — the "where I was" card
  capture/SKILL.md            /brain2:capture — save current context
  search/SKILL.md             /brain2:search <q> — grounded answer from session KB
  explore/SKILL.md            /brain2:explore <p> — force the gap-fill pipeline
  activity/SKILL.md           /brain2:activity <q> — query the cross-repo activity graph
```

**Target resolution** (simpler than Divergence — no active-KB state):
- `project` = current git repo name (`git rev-parse --show-toplevel` basename)
- `kb` = current git branch

Status: **built** — MCP tools, skill Markdown files, plugin manifest
(`.claude-plugin/plugin.json`), local dev marketplace
(`.claude-plugin/marketplace.json`), and the root `.mcp.json` (bare
`{server: {...}}` plugin format) all exist.

**Load it** (local dev marketplace → install → enable; reload the session after):

```
/plugin marketplace add /Users/suherli/Repositories/brain2
/plugin install brain2@brain2
```

The `.mcp.json` runs the MCP server from `backend/`, so that dir needs brain2 +
deps installed (`cd backend && uv sync`).
