# br8n

**One-command capture + instant resume.** br8n saves your thinking before you switch 
away and replays it as a 30-second "where I was" card when you return. No more rebuilding 
context for 9.5 minutes. *(Automatic capture-on-interrupt is a roadmap goal; today you 
checkpoint with one command.)*

Most tools capture *state* (files, layout, git history). br8n captures *intent* — the 
one-line hypothesis in your head: *"JWT validation is caching stale tokens."* That's the 
wedge that matters.

Beyond your current device, br8n is a **portable knowledge engine**: your captured 
insights live in a searchable journal accessible from Claude Code, the iOS companion, or 
any tool that speaks HTTP. Sync, search, and share across machines (paid tier, future).

## Core features

### 1. Capture — Save your thinking before you switch away

Before a meeting, a branch switch, or end of day, run `/br8n:capture`. br8n snapshots 
your workspace in one second and records *"What were you working on?"* — the one-line 
hypothesis is the load-bearing field.

```
Before:                    Capture:                   After:
┌─────────────────┐    /br8n:capture          ┌──────────────────┐
│ Fixing bug in   │  ───► br8n asks:  ───►  │ Finding saved:   │
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

Open br8n (or focus your editor). The resume card appears instantly with:
- Your **last hypothesis** (the headline)
- **Recent snapshots** (how many times were you here?)
- A **coverage band** (how fresh is this knowledge?)

```
╔════════════════════════════════════╗
║ br8n — Where were you?           ║
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

br8n is a self-contained fork of [Delapan](../delapan), repurposing its 
primitives (Findings, pgvector search, tap/preamble) from chat to automatic capture.

## Use it two ways

### Claude Code plugin (on demand)
Slash commands from inside any Claude Code session:

```
/br8n:resume          →  Show the current repo/branch resume card
/br8n:capture         →  Save a snapshot right now
/br8n:search <q>      →  Ask a question, grounded in your session history
/br8n:explore <topic> →  Force the gap-fill pipeline
```

Example: You're in a Claude Code session debugging auth. Type `/br8n:search "how did I set up JWT validation?"` and get an answer from your captured snapshots.

### iOS companion (read on the go)
A native SwiftUI app — the read spine. **Sign in with Apple**, browse your cross-repo 
activity, and read resume cards from your phone. Consumes the same `/v1/projects` + 
`/v1/resume` + `/v1/activity` API, authenticated per-user (see below).

## Knowledge engine: portable & accessible

Your captured snapshots form a **searchable knowledge journal**. The engine runs in two tiers 
from the same code — the difference is where your data lives.

| Tier | Free / local | Paid / cloud |
|---|---|---|
| **Storage** | On-device SQLite | Hosted Supabase (pgvector) |
| **Access** | Loopback only (`localhost:8002`) | Anywhere (with API key) |
| **Sign-in** | None | GoTrue |
| **Data** | `~/.br8n/brain.db` | Encrypted, RLS protected |
| **Select** | `BR8N_BACKEND=local` | `BR8N_BACKEND=cloud` + creds |

**Access your knowledge anywhere:**

```
Claude Code (local/cloud)     iOS companion (cloud)     Browser (cloud, future)
     │                              │                            │
     └──────────────┬───────────────┴───────────────────────┘
                    │
              br8n API
                    │
            ┌───────┴────────┐
            │                │
        SQLite          Supabase
      (local db)      (cloud db)
```

Free tier: single device, no sync. Paid tier: access from Claude Code, the iOS app, or 
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
        /br8n:capture → br8n saves the snapshot
        
15:47 — [Back from meeting]
        /br8n:resume → resume card appears:
        "🔸 JWT validation is caching stale tokens"
        Recent context shown. No "where was I?" moment.
```

### Example 2: Context switch across branches
```
You're on fix/session-timeout, about to switch to main
    /br8n:capture → snapshot saved against this branch
    
Hours later, switch back:
    git checkout fix/session-timeout
    /br8n:resume → resumes from that branch
    → shows the last hypothesis + snapshots
```

### Example 3: In Claude Code
```
You're in a Claude Code session, ask a question:
    /br8n:search "how did I set up the JWT secret?"
    
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
BR8N_BACKEND=local python -m br8n.api.main   # listens 127.0.0.1:8002
```

**Paid/cloud** (Supabase, accessible anywhere):
```bash
BR8N_BACKEND=cloud uvicorn br8n.api.main:app --reload --port 8002
```

Set `OPENAI_API_KEY` for embeddings. Optionally set `TAVILY_API_KEY` for the explore 
pipeline. Data lives in `~/.br8n/brain.db` (local) or Supabase (cloud).

### 2. Claude Code MCP server (optional)

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "br8n": {
      "command": "python",
      "args": ["-m", "br8n.interfaces.mcp.server"],
      "cwd": "/path/to/br8n/backend"
    }
  }
}
```

Then use `/br8n:resume`, `/br8n:capture`, etc. in Claude Code.

## Configuration

By default, the knowledge base is keyed by **project** (git repo name) and **kb** 
(git branch). Override the database path with `BR8N_DB_PATH` (local) or set Supabase 
credentials in `.env` (cloud).

The **cloud tier is multi-user**: each request carries a Supabase GoTrue JWT — 
obtained via **Sign in with Apple** through `POST /v1/auth/apple` (Supabase verifies 
the Apple token and provisions the user) and rotated via `POST /v1/auth/refresh`. The 
backend verifies the JWT against `SUPABASE_JWT_SECRET` and scopes every read/write 
(findings *and* the activity graph) to the caller's own org via row-level security. 
`BR8N_API_KEY` remains as a service-only key for internal callers. The **local tier** 
needs no auth (loopback-only, single user).

## Design principles

- **Intent over state** — capture why, not just what (the hypothesis is the headline)
- **Low friction** — one command checkpoints everything; no forms to fill out
- **Bounded capture** — snapshot at the moments that matter (before a meeting, branch switch, end of day)
- **Survive context switches** — works across folders, branches, machines
- **Never blocking** — capture is fire-and-forget; <1s per snapshot

## Architecture & development

See [`CLAUDE.md`](CLAUDE.md) for:
- Module layout (`br8n/` core engine, fork structure)
- API surface (`/v1/capture`, `/v1/resume`, `/v1/explore`, `/v1/auth/apple`)
- Storage tiers (SQLite vs Supabase)
- MCP tools and plugin skills

## Status

- [x] **Core engine** — capture, resume, explore pipelines
- [x] **Claude Code plugin** — slash commands (`/br8n:resume`, etc.)
- [x] **iOS companion** — native SwiftUI read spine (projects, resume cards, activity)
- [x] **Storage tiers** — free (SQLite) and paid (Supabase) in one codebase
- [x] **Multi-user cloud auth (backend)** — per-user Supabase JWT tenancy, per-org isolation, `/v1/auth/apple` + `/v1/auth/refresh`
- ⬜ **Apple sign-in, end-to-end** — Fly.io deploy + Supabase Apple provider + iOS wiring (designed, in progress)
- ⬜ **Cross-machine sync** — designed, not yet shipped
- ⬜ **Team sharing** — designed, not yet shipped

## License

br8n is open source under the [MIT License](LICENSE) — use it for anything,
including commercially, as long as the copyright notice is preserved.

"br8n" is a name used by Anthony Suherli; the license covers the code, not the
name (see [TRADEMARKS.md](.github/TRADEMARKS.md)). br8n is a self-contained fork of the
Delapan engine; Delapan itself is separately licensed and not covered by this
MIT grant.

Contributions are welcome under the inbound = outbound rule with a DCO sign-off
— see [CONTRIBUTING.md](.github/CONTRIBUTING.md). For the full governance map (security
disclosure, privacy, code of conduct), see [LEGAL.md](.github/LEGAL.md).
