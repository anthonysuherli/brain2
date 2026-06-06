---
name: docs
description: Browse the auto-generated `.br8n/docs/` tree distilled from your session notes — list and read the curated docs, map folders to files, and surface the most relevant ones for the user's question; pass `--rebuild` to force a fresh distill. Use when the user wants to read the project's living docs, find the doc covering a topic, or refresh the tree after new notes landed.
---

# br8n — Docs (browse the living doc tree)

br8n distills the per-KB session notes (see [`/br8n:notes`](../notes/SKILL.md) and
[`../_shared/session-note.md`](../_shared/session-note.md)) into a curated documentation
tree at `<project_path>/.br8n/docs/`. **Notes are the source; docs are the synthesis.**
This skill reads that tree and presents it; `--rebuild` forces a refresh. The tree is
git-ignored and regenerated — never hand-edit it; to change what it says, edit the notes
or the note policy and re-distill.

## Step 0 — Resolve target

`project` = git repo basename, `kb` = git branch, `project_path` = repo root
(see [`../_shared/preamble-first.md`](../_shared/preamble-first.md)):

```bash
basename "$(git rev-parse --show-toplevel)"   # project
git branch --show-current                     # kb
git rev-parse --show-toplevel                 # project_path
```

No prior tap needed — the docs are plain files in the working tree.

## Step 1 — Read the tree

The curated docs are markdown files on disk under `<project_path>/.br8n/docs/`. Read
them with your **own** file tools — they're in the working tree, no MCP call needed:

1. `Glob` for `<project_path>/.br8n/docs/**/*.md` to enumerate the tree.
2. `Read` the files that matter (all of them if small; the relevant subset if large).
3. Present a concise **map** — folders → files — then surface the most relevant doc(s)
   for the user's query or current intent:

   > **Living docs** — `<project>` / `<kb>`
   > - `<folder>/` — `<file>`, `<file>`
   > - `<file>` (top level)
   >
   > Most relevant: `<path>` — `<one-line gist>`

If the tree is **empty or missing**, say so and offer `--rebuild` (Step 2) to generate
it from the notes.

## Step 2 — `--rebuild` (force a refresh)

Trigger when the user passes `--rebuild`, or when the tree is empty/stale. Call:

```
mcp__plugin_br8n_br8n__br8n_distill(
  project, kb, project_path, force=true
)
```

It returns `{distilled, forced, doc_count, folders, ...}`. Report `doc_count` and
`folders` so the user sees what was (re)built, then **re-read** the tree (Step 1) and
present the refreshed map.

Without `--rebuild` this skill only reads; distillation otherwise happens on its own in
the background after each session note (debounced) — you don't need to nudge it.
