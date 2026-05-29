---
name: resume
description: Replay where you left off in this repo+branch as a 30-second resume card — tap the brain2 session KB, surface the latest hypothesis and snapshots, and route on coverage. Use when the user returns to work, asks "where was I", "what was I doing", or wants to rebuild context after an interruption.
---

# brain2 — Resume

The "where I was" card. Pull the most recent captured intent for this repo+branch
into THIS conversation so context recovery takes 30 seconds, not 9.5 minutes.

## Step 0 — Resolve target + tap

Follow [`../_shared/preamble-first.md`](../_shared/preamble-first.md):
`project` = git repo basename, `kb` = git branch. Call
`mcp__brain2__brain2_resume(project, kb, query)` with `query` = whatever the user
is trying to reorient toward (or omit for the synopsis-only spine).

## Step 1 — Lead with the hypothesis

The resume card's wedge is the **latest `hypothesis`** — the one-line intent string
from the most recent snapshot. After the banner, surface it first and large:

> **You were:** `<latest hypothesis>`

Then the supporting context, tersely:
- **Branch / files** — `cursor_file:cursor_line`, open files from the snapshot.
- **In flight** — `git_diff_stat`, terminal tail if present.
- **Synopsis** — the `<N>` standing topics, titles only.

## Step 2 — Route on coverage

- **rich / sparse** → you have a card; offer the obvious next action (resume the
  hypothesis, open the cursor file).
- **gap** → no captured context for this branch yet. Say so and offer
  `/brain2:capture` (to start tracking) or `/brain2:explore <topic>` (to seed the
  KB from the web).

Read-only op — no loop-back needed unless the user states new intent worth saving,
in which case offer `/brain2:capture`.
