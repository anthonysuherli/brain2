---
name: search
description: Ground a question in the brain2 session KB, fill the gap from the web if needed, then answer — the ground → grow → answer front door. Use by default when the user asks a question against what this repo+branch session knows; reach for /brain2:resume or /brain2:explore directly only when you want exactly one step.
---

# brain2 — Search

The primary verb. Answer the user's question from the session KB, and if the KB is
thin on it, fill the gap online *before* answering. One skill, three moves:
**ground → grow → answer.**

## Step 1 — Ground

Follow [`../_shared/preamble-first.md`](../_shared/preamble-first.md): resolve
`project`/`kb` from git, then `mcp__plugin_brain2_brain2__brain2_resume(project, kb, query=<the
user's question>)`. Show the banner + resume card. Note the `coverage` band.

## Step 2 — Grow (conditional)

Branch on `coverage` for the question:

- **rich** → skip web research; the KB already covers it. Go to answer.
- **sparse** → the KB partially covers it. Decide if the gap is material to a
  faithful answer. If yes, run a **narrow** `/brain2:explore` (see
  [`../explore/SKILL.md`](../explore/SKILL.md)) targeting only the thin slice; if
  no, answer from what's there and flag the soft spot.
- **gap** → nothing to ground on. Either run `mcp__plugin_brain2_brain2__brain2_explore(project,
  kb, prompt=<question>)` to gap-fill (blocks 1–3 min, then re-tap), or, if the
  user wants a fast answer, say the KB is empty on this and answer from general
  knowledge with that caveat.

Only grow when the gap actually blocks a good answer — don't explore reflexively.

## Step 3 — Answer

Answer the user's question from the assembled context (resume card + any fresh
findings). Cite which findings/snapshots grounded the answer. If you explored, the
new findings are already persisted — mention the next resume will be richer.
