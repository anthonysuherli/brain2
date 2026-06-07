---
name: timeline
description: Read back your append-only activity timeline for this repo+branch — a chronological log of session notes, context captures, and journal entries. Shows recent activity (last few days) by default, with the past-week view and the full all-time scroll alongside. Pass `--rebuild` to force a fresh rollup now. Use when the user asks "what have I been doing", wants a chronological work log, a daily/weekly recap, or to scroll their activity history.
---

# br8n — Timeline (append-only activity log)

br8n periodically rolls this repo+branch's **session notes**, **context captures**, and
**journal entries** into a chronological, append-only timeline at
`<project_path>/.br8n/timeline/`:

- `all-time.md` — the canonical append-only log (newest at the bottom, never rewritten).
- `recent.md` — the last few days (regenerated each pass).
- `week.md` — the past week (regenerated each pass).

This is the **temporal** view — distinct from `/br8n:docs` (the topical doc tree) and
`/br8n:activity` (the cross-repo work graph). The files are git-ignored and regenerated;
never hand-edit them — they rebuild from notes/captures/journal.

## Step 0 — Resolve target

`project` = git repo basename, `kb` = git branch, `project_path` = repo root
(see [`../_shared/preamble-first.md`](../_shared/preamble-first.md)):

```bash
basename "$(git rev-parse --show-toplevel)"   # project
git branch --show-current                     # kb
git rev-parse --show-toplevel                 # project_path
```

No prior tap needed — the timeline is plain files in the working tree.

## Step 1 — Read and present

The timeline files are markdown on disk under `<project_path>/.br8n/timeline/`. Read
them with your **own** file tools — no MCP call needed to read:

1. `Read` `<project_path>/.br8n/timeline/recent.md` and present it (newest at the
   bottom — the "scrolling down" feel).
2. Point the user at the wider views: `week.md` (past week) and `all-time.md` (the full
   scroll). `Read` and surface those too if the user asks for more history.

If the dir is **empty or missing**, say so and offer `--rebuild` (Step 2) to build it
from the notes/captures/journal so far.

## Step 2 — `--rebuild` (force a pass)

Trigger when the user passes `--rebuild`, or when the dir is empty/stale. Call:

```
mcp__plugin_br8n_br8n__br8n_timeline(
  project, kb, project_path, force=true
)
```

It returns `{forced, appended, recent_days, week_days, all_time_path, recent_path,
week_path}`. Report `appended` (how many new events landed in the all-time log) and the
window sizes, then **re-read** `recent.md` (Step 1) and present the refreshed view.

Without `--rebuild` this skill only reads; the rollup otherwise happens on its own in the
background after notes/captures (debounced) — you don't need to nudge it.
