---
name: capture
description: Save the current workspace context to the brain2 session KB as a snapshot — branch, open/cursor files, git diff stat, and a one-line hypothesis of what you're doing. Use when the user is about to switch away, says "save my context", "remember where I am", or wants to checkpoint intent before an interruption.
---

# brain2 — Capture

Persist a workspace snapshot so a later `/brain2:resume` can replay it. The snapshot
becomes a Finding in the repo+branch KB. The load-bearing field is the
**`hypothesis`** — a one-line statement of current intent; it makes recovery 3–5×
faster, so always try to fill it.

## Step 0 — Resolve target

`project` = git repo basename, `kb` = git branch
(see [`../_shared/preamble-first.md`](../_shared/preamble-first.md)). No prior tap
needed — capture is a pure write.

## Step 1 — Gather workspace state

Collect from the environment (skip any that fail — all are optional except trigger
and captured_at):

```bash
git rev-parse --show-toplevel        # project_path / repo
git branch --show-current            # branch
git diff --stat                      # git_diff_stat
```

- `captured_at` — current ISO-8601 timestamp.
- `trigger` — `"manual"` for a user-invoked capture (other values: `blur`,
  `checkout`, `idle`, `note`).
- `cursor_file` / `cursor_line` / `open_files` — from the user if they mention what
  they're editing; otherwise omit.
- `terminal_tail` — last relevant command output if the user pastes it.

## Step 2 — Write the hypothesis, then capture

If the user gave intent ("I'm tracking down the auth race"), use it verbatim as
`hypothesis`. If not, **infer one** from the diff stat + recent conversation and
**confirm it in one line** before saving — a wrong hypothesis is worse than none.

Then call:

```
mcp__plugin_brain2_brain2__brain2_capture(
  project, kb, trigger="manual", captured_at=<iso>,
  branch, git_diff_stat, cursor_file?, cursor_line?, open_files?,
  hypothesis=<the one-liner>, project_path=<repo path>
)
```

## Step 3 — Confirm

Report the returned `finding_id` and echo the saved hypothesis so the user knows
exactly what a future resume will replay.
