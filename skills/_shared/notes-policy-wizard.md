# notes-policy-wizard  (co-design what session notes capture — one question at a time)

Co-design the per-KB **note policy** *with the user*: the section template the
end-of-session note fills (`## Decisions`, `## Changes`, …) and the free-text **steer**
that says what to emphasize or skip. Modeled on
[`kg-schema-wizard.md`](kg-schema-wizard.md): a short interview, **one multiple-choice
question at a time** via `AskUserQuestion`, then persist at a turn boundary. Notes
themselves are written later by the `Stop` hook (see
[`session-note.md`](session-note.md)) — this wizard only sets the rules they follow.

**Opt-in only.** This wizard runs *only* when the user invokes `/br8n:notes --wizard`.
It is never auto-launched, never surfaced mid-flow. Like every br8n gated decision:
the user opts in; offer once, then go quiet — don't re-raise it on later sessions.

## Stage 0 — Resolve target + load the current policy

Resolve `project` / `kb` / `project_path` per [`preamble-first.md`](preamble-first.md).
Then call
`mcp__plugin_br8n_br8n__br8n_notes_policy_get(project, kb, project_path)` →
`{policy: {sections: [{name, enabled}], steer}, …}`. This is the **starting point** —
the draft you reshape with the user, not a blank slate. Keep an internal working copy
of `sections` + `steer` that each stage edits.

## Stage 1 — Sections to keep (one question)

Show the current section list. `AskUserQuestion`: *"Which sections should the session
note keep?"* — offer the existing sections as multi-select-style options (e.g. *keep
all*, *Decisions + Changes only*, *drop Open questions*), each option a complete answer
with a one-line trade-off (what you'd lose by dropping it). Apply the choice to the
working `sections` (flip `enabled`, don't delete — disabled sections stay in the
template).

## Stage 2 — Sections to add (one question)

`AskUserQuestion`: *"Anything the note should also capture?"* — offer 2–4 concrete
candidate sections drawn from this KB's work (e.g. *Risks / follow-ups*, *Test results*,
*API changes*, *Nothing — the set is complete*). For each picked option append a new
`{name, enabled: true}` to the working `sections`. "Other" lets the user name their own.

## Stage 3 — Detail level + what to skip (one question)

`AskUserQuestion`: *"How detailed, and what should it skip?"* — 2–4 options pairing a
detail level with a skip rule, e.g. *terse, decisions only*; *normal, skip routine dep
bumps*; *thorough, include rationale*. The choice becomes the **seed of the steer** —
record it as a clear sentence in the working `steer`.

## Stage 4 — Free-text steer (optional, one question)

`AskUserQuestion`: *"Add any free-text guidance for the note-writer?"* — options like
*emphasize architecture decisions*, *flag anything left unfinished*, *no extra guidance*,
plus "Other" for the user's own words. Merge the answer into the working `steer` (append
to Stage-3's sentence; don't overwrite it).

## Stage 5 — Confirm + persist (turn boundary)

Present the **full proposed policy** — the final section list (each marked
enabled/disabled) and the steer text — and `AskUserQuestion`: *approve as-is / adjust
sections / reword the steer*. Apply edits and re-present until the user explicitly
approves.

Only then persist:
`mcp__plugin_br8n_br8n__br8n_notes_policy_set(project, kb, project_path, policy=<the approved {sections, steer}>)`.
- On `{ok: false, errors}` — show the errors, fix **with the user**, retry. Nothing is
  saved until valid.
- On `{ok: true}` — confirm by echoing the saved policy from the response (sections +
  steer), and note that the next end-of-session note will follow it. Then stop — don't
  re-offer the wizard.
