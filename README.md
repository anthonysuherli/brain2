# brain2

**Context resume for developers.** brain2 eliminates the ~9.5-minute context-rebuild
tax: it captures what you were thinking at the moment of interruption and replays it
as a 30-second "where I was" card when you return.

Every tool saves your *state* (open files, layout). None save your *intent* — the
one-line hypothesis in your head when the meeting pulled you away. That's the wedge
brain2 owns.

```
⚡ Interruption ──► Capture → Finding ──► KB (pgvector) ──► Resume card
  blur · checkout      open files, cursor,    reasoning        30-sec
  · idle               git diff, hypothesis   journal          "where I was"
```

## How it works

1. **Capture** — when you're interrupted (window blur, `git checkout`, long idle),
   brain2 snapshots your workspace and asks one skippable question: *"What were you
   working on?"* The snapshot is stored as an embedded Finding.
2. **Resume** — when you come back, the resume card appears automatically: your last
   hypothesis up top, recent snapshots, and a coverage band.
3. **Explore** — if the card's coverage is `gap`, one click runs a web-research
   pipeline to pull in fresh external context (changed deps, new issues, docs) and
   folds it back into your knowledge base.

brain2 is a self-contained fork of the [Divergence](../divergence) engine, repurposing
its primitives from chat-authoring to automatic session capture: **Findings** become
session snapshots, **pgvector search** becomes the searchable reasoning journal, and
**tap / preamble** becomes the resume card.

## Two ways to use it

### VS Code extension (automatic)

Capture triggers and the resume-card webview live in the editor. Interruptions are
detected automatically; the card pops up on focus-regain.

### Claude Code plugin (on demand)

Slash commands call the same engine from inside a Claude Code session:

| Command | What it does |
|---|---|
| `/brain2:resume` | Show the "where I was" card for the current repo/branch |
| `/brain2:capture` | Save the current context as a snapshot |
| `/brain2:search <q>` | Ask a question grounded in your captured session history |
| `/brain2:explore <p>` | Force the gap-fill web-research pipeline |

> The Claude Code plugin skills are built and available (`skills/`: capture, resume,
> search, explore); the MCP tools they call (`brain2_capture`, `brain2_resume`,
> `brain2_explore`) are built and usable today.

## Free vs Paid

brain2 runs in two tiers from one engine — the difference is **where your data
lives and how you sign in**, not what the engine does.

| | Free / local | Paid / cloud |
|---|---|---|
| Storage | On-device SQLite (`~/.brain2/brain.db`) | Hosted Supabase (pgvector + RLS) |
| Account | None — single device, no login | GoTrue sign-in |
| API keys | Bring your own (`OPENAI_API_KEY`, optional `TAVILY_API_KEY`) | Managed (future) |
| API server | Loopback (`127.0.0.1`), no API key | Pre-shared `BRAIN2_API_KEY` |
| Select via | `BRAIN2_BACKEND=local` | `BRAIN2_BACKEND=cloud` + Supabase creds |

The paid differentiators — cross-machine **sync**, **cross-repo search**, **managed
keys**, and **team sharing** — are designed but **not yet shipped**. The cloud tier
today is the Supabase backend with GoTrue login.

## Quick start

### 1. Backend

`uv` is optional — plain `venv` works. The local tier needs `sqlite-vec`.

```bash
cd backend
python3.11 -m venv .venv          # or: uv venv
.venv/bin/pip install -e ".[dev]" sqlite-vec
cp .env.example .env              # pick the FREE or PAID block (see the file)
```

**Free / local** (SQLite, no account, no API key) — use the blessed launcher; it
enforces loopback binding because the local tier disables API auth:

```bash
BRAIN2_BACKEND=local python -m brain2.api.main   # binds 127.0.0.1:8002
```

Set `OPENAI_API_KEY` (embeddings) and, optionally, `TAVILY_API_KEY` (explore) in
`.env`. Data lives in `~/.brain2/brain.db` (override with `BRAIN2_DB_PATH`).

**Paid / cloud** (Supabase + API key):

```bash
uvicorn brain2.api.main:app --reload --port 8002
```

The cloud backend shares the same Supabase instance and schema as Divergence — apply
the migrations in `supabase/migrations/` if you're starting fresh, and set
`BRAIN2_API_KEY=brain2_live_<anything>` plus the Supabase creds in `.env`.

### 2. VS Code extension

```bash
cd vscode-extension
npm install && npm run build
```

Open the `vscode-extension/` folder in VS Code and press **F5** to launch the
Extension Development Host. In that window, run **`brain2: Sign In`** and paste your
`BRAIN2_API_KEY`.

### 3. Claude Code MCP server (optional)

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "brain2": {
      "command": "python",
      "args": ["-m", "brain2.interfaces.mcp.server"],
      "cwd": "/Users/suherli/Repositories/brain2/backend",
      "env": { "PYTHONPATH": "/Users/suherli/Repositories/brain2/backend" }
    }
  }
}
```

## Configuration

By default the knowledge base is keyed by **project = workspace folder name** and
**KB = current git branch**. Override in VS Code `settings.json`:

```json
{
  "brain2.apiUrl": "http://localhost:8002",
  "brain2.project": "my-project",
  "brain2.kb": "session",
  "brain2.idleThresholdSeconds": 300,
  "brain2.enableBlurTrigger": true,
  "brain2.enableGitCheckoutTrigger": true,
  "brain2.enableIdleTrigger": true
}
```

## Design principles

1. **Capture intent, not just state** — the one-line hypothesis is the headline.
2. **Zero manual maintenance** — auto-snapshot on interruption; no daily rituals.
3. **Bounded, summarized capture** — deltas at moments that matter; never always-on recording.
4. **Survive the context boundary** — works across folder, branch, and machine switches.
5. **Sub-second, never blocking** — capture is async; if it takes a moment, it's abandoned.

## Architecture

See [`CLAUDE.md`](CLAUDE.md) for the engineering guide — fork conventions, module
layout, API surface, and the MCP tool / plugin-skill mapping.

## Status

- [x] Phase 0 — Engine fork (Supabase, pgvector, Finding, preamble/tap)
- [x] Phase 1 — VS Code extension (triggers, capture, resume card)
- [x] Phase 2 — Resume card polish (hypothesis prominent, auto-resume on focus)
- [x] Phase 3 — Always-open explore seam (gap-band → pipeline → auto-refresh)
- [x] Claude Code plugin skills (`skills/` Markdown)
