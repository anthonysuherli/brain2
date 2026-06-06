---
name: notes
description: Dictate what kind of session notes br8n takes for this repo+branch — show the current note policy (section template + steer), edit it inline with free-text guidance, or launch a guided wizard to co-design it. Use when the user wants to control what end-of-session notes capture ("focus on architecture", "skip dep bumps"), review the policy, or set it up from scratch with `--wizard`.
---

# br8n — Notes (steer the session-note policy)

br8n writes a session note at the end of every conversation
(see [`../_shared/session-note.md`](../_shared/session-note.md) — fired by the `Stop`
hook, best-effort, never blocking). What goes *into* that note is governed by a per-KB
**policy**: a section template (`## Decisions`, `## Changes`, …) plus a free-text
**steer** ("emphasize architecture, skip dependency bumps"). This skill is how you read
and shape that policy. It does **not** write a note itself — it only changes the rules
the next session note follows.

## Step 0 — Resolve target

`project` = git repo basename, `kb` = git branch, `project_path` = repo root
(see [`../_shared/preamble-first.md`](../_shared/preamble-first.md)):

```bash
basename "$(git rev-parse --show-toplevel)"   # project
git branch --show-current                     # kb
git rev-parse --show-toplevel                 # project_path
```

No prior tap needed — policy read/write is independent of KB coverage.

## Mode select — branch on the args

| Invocation | Mode | Do |
|---|---|---|
| `/br8n:notes` (no args) | **Show** | Step A — print the current policy |
| `/br8n:notes <free text>` | **Steer** | Step B — set the steer to that text |
| `/br8n:notes --wizard` | **Wizard** | Step C — run the guided co-design |

## Step A — Show the current policy

Call
`mcp__plugin_br8n_br8n__br8n_notes_policy_get(project, kb, project_path)`.
It returns `{policy: {sections: [{name, enabled}], steer}, project, kb}` (the default
policy if none is set yet). Render it readably:

> **Note policy** — `<project>` / `<kb>`
> Sections the next note will use:
> - `<name>` — enabled / disabled
> Steer: `<steer, or "(none)">`

Then mention the two ways to change it: pass free text to set a steer, or
`--wizard` to redesign the section template.

## Step B — Set the steer from free text

The args are the new steer (e.g. `/br8n:notes focus on architecture, skip dep bumps`).

1. `br8n_notes_policy_get(project, kb, project_path)` — fetch the current policy.
2. Keep its `sections` exactly as-is; replace `steer` with the user's text.
3. `mcp__plugin_br8n_br8n__br8n_notes_policy_set(project, kb, project_path, policy=<updated>)`.
   On `{ok: false, errors}` show the errors, fix, and retry — nothing is saved until
   valid. On `{ok: true}` confirm: echo the new steer and the (unchanged) section list
   so the user sees exactly what the next session note will honor.

## Step C — Run the guided wizard

Hand off to [`../_shared/notes-policy-wizard.md`](../_shared/notes-policy-wizard.md) —
the one-question-at-a-time loop that co-designs the section template + steer and persists
via `br8n_notes_policy_set` at a turn boundary. The wizard only runs on an explicit
`--wizard` (the user opts in); it is never auto-launched.
