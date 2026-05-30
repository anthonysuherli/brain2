---
name: activity
description: Query your cross-repo ACTIVITY knowledge graph — what you've been working on across all repos (repos touched, branches, files, work sessions, and the tasks behind them). Use when the user asks "what was I working on", "what have I touched lately", "what's connected to <file/repo>", or wants a cross-repo rollup rather than a single repo+branch resume.
---

# brain2 — Activity

The cross-repo lens. While `/brain2:resume` replays one repo+branch, **activity**
answers "what have I been doing, everywhere" — backed by a knowledge graph that
accumulates automatically on every `brain2_capture`. Nothing to build; just query.

The graph's ontology: **repo, branch, file, session, task** nodes, related by
`on_repo`, `on_branch`, `in_repo`, `edited`, `viewed`, `pursued`.

## Step 1 — Query the graph

Call `mcp__plugin_brain2_brain2__brain2_activity`:

- A natural-language `query` seeds a **semantic subgraph** ("what touches the
  store layer", "the KG work"). Omit it for the whole (capped) graph.
- Optional `repo` narrows to one repository.

It returns `{nodes, edges, summary}` — `summary` is a ready-to-show natural-language
rollup; `nodes`/`edges` are the graph slice for anything more detailed.

## Step 2 — Answer

Lead with the `summary` (repos, tasks, files in view). Then, if the user wants
specifics, read the `nodes`/`edges`:

- **Tasks** (`type: task`) — the intents pursued, distilled from hypotheses.
- **Sessions** (`type: session`) — individual captures; `properties` carry
  `captured_at`, `repo`, `branch`, `hypothesis`.
- **Files** (`type: file`) — what was edited vs. viewed (the edge `relation`).
- Follow `edited`/`pursued`/`on_repo` edges to connect a file or task back to the
  repos and sessions that touched it.

## When to reach elsewhere

- Single repo+branch "where was I" → `/brain2:resume` (richer card for the here-and-now).
- A question needing external knowledge → `/brain2:search` (grounds + fills the gap).

The activity graph is read-only here — it grows on its own as captures happen.
