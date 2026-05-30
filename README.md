# brain2

**Context resume + one-click capture.** brain2 auto-saves your thinking when interrupted 
and replays it as a 30-second "where I was" card when you return. No more rebuilding 
context for 9.5 minutes.

Most tools capture *state* (files, layout, git history). brain2 captures *intent* — the 
one-line hypothesis in your head: *"JWT validation is caching stale tokens."* That's the 
wedge that matters.

Beyond your current device, brain2 is a **portable knowledge engine**: your captured 
insights live in a searchable journal accessible from VS Code, Claude Code, or any tool 
that speaks HTTP. Sync, search, and share across machines (paid tier, future).

## Core features

### 1. Capture — Save your thinking on interruption

When interrupted (window blur, branch switch, long idle), brain2 snapshots your workspace 
in one second and asks: *"What were you working on?"* (optional)

```
Before:                    Interrupt:                 After:
┌─────────────────┐       (window blur)        ┌──────────────────┐
│ Fixing bug in   │  ───► brain2 asks:  ───►  │ Finding saved:   │
│ auth flow       │       "What were    │      │ • git diff       │
│ files: [3]      │       you doing?"   │      │ • open files     │
│ branch: fix-#42 │       Fixing auth   │      │ • cursor pos     │
└─────────────────┘       bug            │      │ • hypothesis     │
                                         └──────────────────┘
                                         (stored in KB)
```

Your captured snapshots live in a searchable journal. One hypothesis per snapshot—
the thing you'd write on a post-it.

### 2. Resume — Return to where you left off

Open brain2 (or focus your editor). The resume card appears instantly with:
- Your **last hypothesis** (the headline)
- **Recent snapshots** (how many times were you here?)
- A **coverage band** (how fresh is this knowledge?)

```
╔════════════════════════════════════╗
║ brain2 — Where were you?           ║
╠════════════════════════════════════╣
║ 📌 Fixing auth bug in login flow   ║
║                                    ║
║ Recent snapshots:                  ║
║   • 5 min ago: auth middleware     ║
║   • 12 min ago: jwt validation     ║
║   • 45 min ago: session storage    ║
║                                    ║
║ Coverage: ████░ (rich)             ║
╚════════════════════════════════════╝
```

No digging through git logs. No "where was I again?" Back to work in 30 seconds.

### 3. Explore — Fill knowledge gaps

If coverage is `gap` (you've been away a while, or switched branches), one click runs 
a web-research pipeline to pull in fresh context: changed docs, new issues, updated 
deps—and folds it back into your session knowledge base.

```
Resume card says "coverage: gap"
         │
         ▼
┌─────────────────┐
│ [Explore Now]   │  ─► web search (changed deps, docs)
└─────────────────┘  ─► fetch + parse relevant sources
         │            ─► extract + embed findings
         ▼
Coverage updates to "rich" + new context appears in the card
```

Perfect for returning after a weekend or after your teammate merged a big change.

---

brain2 is a self-contained fork of [Divergence](../divergence), repurposing its 
primitives (Findings, pgvector search, tap/preamble) from chat to automatic capture.

## Use it two ways

### VS Code extension (automatic)
Interruptions are detected automatically. The resume card pops up when you refocus. 
Captures trigger on window blur, `git checkout`, or idle timeout.

**What you see:**
```
You get interrupted → … back to VS Code → resume card appears (auto)
                     (30-second "where I was" card)
```

### Claude Code plugin (on demand)
Slash commands from inside any Claude Code session:

```
/brain2:resume          →  Show the current repo/branch resume card
/brain2:capture         →  Save a snapshot right now
/brain2:search <q>      →  Ask a question, grounded in your session history
/brain2:explore <topic> →  Force the gap-fill pipeline
```

Example: You're in a Claude Code session debugging auth. Type `/brain2:search "how did I set up JWT validation?"` and get an answer from your captured snapshots.

## Knowledge engine: portable & accessible

Your captured snapshots form a **searchable knowledge journal**. The engine runs in two tiers 
from the same code — the difference is where your data lives.

| Tier | Free / local | Paid / cloud |
|---|---|---|
| **Storage** | On-device SQLite | Hosted Supabase (pgvector) |
| **Access** | Loopback only (`localhost:8002`) | Anywhere (with API key) |
| **Sign-in** | None | GoTrue |
| **Data** | `~/.brain2/brain.db` | Encrypted, RLS protected |
| **Select** | `BRAIN2_BACKEND=local` | `BRAIN2_BACKEND=cloud` + creds |

**Access your knowledge anywhere:**

```
VS Code extension (local)     Claude Code (cloud)       Browser (cloud, future)
     │                              │                            │
     └──────────────┬───────────────┴───────────────────────┘
                    │
              brain2 API
                    │
            ┌───────┴────────┐
            │                │
        SQLite          Supabase
      (local db)      (cloud db)
```

Free tier: single device, no sync. Paid tier: access from VS Code, Claude Code, or 
any tool that speaks HTTP. Team sharing and cross-repo search are designed (future).

The paid value props — **cross-machine sync**, **cross-repo search**, **managed keys**, 
**team sharing** — are not yet shipped.

## Examples

### Example 1: The meeting interruption
```
14:32 — Debugging auth middleware
        Open file: middleware.py, line 45
        Hypothesis: "JWT validation is caching stale tokens"
        
14:35 — [Meeting call]
        VS Code blur → brain2 captures snapshot
        
15:47 — [Back from meeting]
        Focus VS Code → resume card appears:
        "🔸 JWT validation is caching stale tokens"
        Recent context shown. No "where was I?" moment.
```

### Example 2: Context switch across branches
```
You're on main, work is on fix/session-timeout
You switch branches → capture fires
    
Hours later, switch back:
    git checkout fix/session-timeout
    → brain2 resumes from that branch
    → shows the last hypothesis + snapshots
```

### Example 3: In Claude Code
```
You're in a Claude Code session, ask a question:
    /brain2:search "how did I set up the JWT secret?"
    
Claude Code queries your captured session history
    and answers from your own notes/decisions.
```

---

## Quick start

### 1. Backend setup

The local tier needs `sqlite-vec`; cloud tier needs Supabase creds (optional).

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]" sqlite-vec
cp .env.example .env
```

**Start the API:**

**Free/local** (SQLite, single device):
```bash
BRAIN2_BACKEND=local python -m brain2.api.main   # listens 127.0.0.1:8002
```

**Paid/cloud** (Supabase, accessible anywhere):
```bash
BRAIN2_BACKEND=cloud uvicorn brain2.api.main:app --reload --port 8002
```

Set `OPENAI_API_KEY` for embeddings. Optionally set `TAVILY_API_KEY` for the explore 
pipeline. Data lives in `~/.brain2/brain.db` (local) or Supabase (cloud).

### 2. VS Code extension

```bash
cd vscode-extension
npm install && npm run build
```

Open `vscode-extension/` in VS Code, press **F5** to launch the extension host.

Run **`brain2: Sign In`** and paste your `BRAIN2_API_KEY` (or leave blank for local tier).

### 3. Claude Code MCP server (optional)

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "brain2": {
      "command": "python",
      "args": ["-m", "brain2.interfaces.mcp.server"],
      "cwd": "/path/to/brain2/backend"
    }
  }
}
```

Then use `/brain2:resume`, `/brain2:capture`, etc. in Claude Code.

## Configuration

By default, the knowledge base is keyed by **project** (workspace folder name) and 
**kb** (git branch). Customize in VS Code `settings.json`:

```json
{
  "brain2.apiUrl": "http://localhost:8002",
  "brain2.project": "my-project",
  "brain2.kb": "my-session",
  "brain2.idleThresholdSeconds": 300,
  "brain2.enableBlurTrigger": true,
  "brain2.enableGitCheckoutTrigger": true
}
```

Override the database path with `BRAIN2_DB_PATH` (local) or set Supabase credentials 
in `.env` (cloud).

## Design principles

- **Intent over state** — capture why, not just what (the hypothesis is the headline)
- **Zero friction** — auto-capture on interrupt; no manual save buttons
- **Bounded capture** — snapshots at moments that matter (blur, branch switch, idle)
- **Survive context switches** — works across folders, branches, machines
- **Never blocking** — capture is fire-and-forget; <1s per snapshot

## Architecture & development

See [`CLAUDE.md`](CLAUDE.md) for:
- Module layout (`brain2/` core engine, fork structure)
- API surface (`/v1/capture`, `/v1/resume`, `/v1/explore`)
- Storage tiers (SQLite vs Supabase)
- MCP tools and plugin skills

## Status

- [x] **Core engine** — capture, resume, explore pipelines
- [x] **VS Code extension** — auto-triggers, resume card webview
- [x] **Claude Code plugin** — slash commands (`/brain2:resume`, etc.)
- [x] **Storage tiers** — free (SQLite) and paid (Supabase) in one codebase
- ⬜ **Cross-machine sync** — designed, not yet shipped
- ⬜ **Team sharing** — designed, not yet shipped
