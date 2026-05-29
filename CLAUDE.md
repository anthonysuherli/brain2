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
- `brain2/api/` — FastAPI: `/v1/capture`, `/v1/resume/{project}/{kb}`, `/v1/explore/...`
- `brain2/interfaces/mcp/server.py` — MCP tools: `brain2_capture`, `brain2_resume`, `brain2_explore`
- `vscode-extension/` — VS Code extension (capture triggers + resume card webview)
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
- `knowledge_graph/` — KG builder (not used by the capture/resume loop)
- `monitoring/service.py`, `monitoring/report.py` — only `recorder.py` is copied

## Setup

```bash
# Install backend
cd backend
uv venv && uv sync

# Copy .env and fill in values (shared with divergence Supabase instance)
cp .env.example .env

# Run the API server
uvicorn brain2.api.main:app --reload --port 8002

# Run the MCP server (add to .claude/settings.json)
python -m brain2.interfaces.mcp.server
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
- Auth: pre-shared API key (`BRAIN2_API_KEY` in .env = `brain2.apiKey` in VS Code secrets)
- Supabase: same instance and schema as divergence (no migration divergence)
- KB naming: project = workspace folder name, kb = git branch name

## Phase status

- [x] Phase 0 — Engine fork (Supabase, pgvector, Finding, preamble/tap)
- [x] Phase 1 — VS Code extension scaffold (triggers, capture, resume card)
- [x] Phase 2 — Resume card polish (hypothesis prominent, snapshot count, auto-resume on focus)
- [x] Phase 3 — Always-open explore seam (gap-band → explore pipeline → auto-refresh card)

## API surface

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Health check |
| `/v1/capture` | POST | Save a workspace snapshot as a Finding |
| `/v1/resume/{project}/{kb}` | GET | Tap KB → 30-sec resume card HTML + preamble |
| `/v1/explore/{project}/{kb}` | POST | Start gap-fill pipeline (returns exploration_id) |
| `/v1/explore/{id}/status` | GET | Poll exploration progress + results |

## MCP tools (for Claude Code)

| Tool | Purpose |
|---|---|
| `brain2_capture` | Persist a workspace snapshot |
| `brain2_resume` | Tap KB → resume card (preamble + coverage) |
| `brain2_explore` | Run gap-fill pipeline synchronously (blocks ~1-3 min) |

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
