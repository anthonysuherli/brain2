# brain2 Living Docs — design

**Date:** 2026-06-03
**Status:** Design (validated via brainstorming; not yet implemented)
**Working name:** Living Docs

## Summary

brain2 grows a third memory surface alongside snapshots and the activity-KG: a
**two-layer, self-maintaining documentation tree on disk** that auto-generates and
updates as the user works. Plus a **background auto-capture agent** that keeps the
journal warm without the user lifting a finger.

Everything here obeys the project's **non-blocking-by-default** philosophy: work
happens in the background, around the user's turn, and fails silent. Human decisions
(note policy) are gated to turn boundaries via a wizard.

## The two layers

**Layer 1 — Session notes (the source).** One note per Claude Code conversation,
finalized at session end. Each note is **both**:

- a **Finding** (`category="note"`, embedded, searchable) — so resume, search, and
  the activity-KG immediately get richer with no new query path;
- a rendered markdown file at `.brain2/notes/<kb>/<timestamp>-<slug>.md`.

Notes are **append-only** — a faithful journal of what happened, never rewritten.

**Layer 2 — Curated doc tree (the synthesis).** A deduped, organized knowledge base
distilled *from* the note-Findings into `.brain2/docs/…`. These files are **rendered
output only — never re-ingested as Findings**. (Re-ingesting would create a
distill-its-own-output drift loop where each pass re-distills its own synthesis.) The
KB is the source of truth; the doc tree is the maintained view.

## On-disk layout

All under repo-root `.brain2/`, **git-ignored** (a per-developer working set,
co-located with code for easy reading, never committed — no PR noise):

```
.brain2/
  notes/<kb>/2026-06-03-1430-fix-auth-race.md   # raw journal, 1 per session
  docs/                                          # curated synthesis
    <inferred-folders>/…                         # flat until taxonomy emerges
  notes-policy.json                              # per-KB note template + steer
  docs-state.json                                # taxonomy + debounce bookkeeping
```

`kb` = git branch; co-located with the existing `(project, kb)` model.

## Folder structure — inferred, schema-optional

The doc-tree folder structure is **inferred from note content** by an evolving
LLM-proposed taxonomy:

- **Flat** (everything directly under `docs/`) until enough notes exist to cluster
  meaningfully. This satisfies the "no schema yet → one directory" requirement.
- Once clustering is warranted, the distiller proposes and evolves a taxonomy,
  recorded in `docs-state.json`.
- If a **user schema is set** (the existing per-KB `KGSchema`, or a future doc-layout
  schema), it **constrains/overrides** the inferred layout rather than the inference
  starting from scratch.

## Runtime — three background loops

All honor "non-blocking, fails silent": a failure degrades to "do nothing visible."

### 1. Auto-capture loop — CC-session-scoped, change-driven

- A **`SessionStart` hook** launches `Agent(run_in_background)` running a capture watch
  that lives for the Claude Code session and dies on `SessionEnd`.
- Each tick (default ~3 min, `BRAIN2_AUTO_CAPTURE_INTERVAL`): read
  `git rev-parse`/`git diff --stat`/branch + recent files; compare against a
  `last-snapshot` fingerprint.
- **Unchanged → no-op.** **Changed →** distill a one-line hypothesis from the diff and
  `POST /v1/capture` (the existing capture path). Feeds Findings + activity-KG exactly
  as today.
- Restores the always-on journal lost when the VS Code extension was removed. No
  daemon, tier-agnostic, no duplicate-snapshot noise.

### 2. Session-note write — once per conversation

A **`Stop`/`SessionEnd` hook** fires the note author:

- **Agent-rich path:** the CC agent, still holding the full conversation in context,
  writes the note per the KB's `notes-policy.json` (template + steer) → persists a
  `note` Finding *and* writes the `.brain2/notes/<kb>/…` file. Best quality —
  captures decisions and reasoning, not just structural diffs.
- **Backend-fallback path:** if no agent note exists for the session (e.g. capture
  came from another surface), the backend distills a thinner note from the session's
  snapshots — same shape, lower confidence.

This is the **hybrid** model: agent-rich when a session ran through CC, backend
fallback otherwise. Best coverage; two code paths.

### 3. Distill loop — debounced, after notes land

A **background agent** re-distills the curated tree when `N` new notes
(`BRAIN2_DISTILL_DEBOUNCE_N`) **or** `T` elapsed (`BRAIN2_DISTILL_DEBOUNCE_T`) since
the last run (tracked in `docs-state.json`). It:

- reads note-Findings,
- updates the inferred taxonomy (or honors the user schema),
- writes/moves **only affected files** under `.brain2/docs/`,
- **never re-ingests its output.**

Debouncing keeps it from running every session and bounds cost/file churn; a full
taxonomy reshuffle happens only occasionally. `/brain2:docs --rebuild` is the
on-demand escape hatch.

## Note policy — template + free-text steer, with a wizard

The user dictates "what kind of notes get taken" per repo+branch via
`notes-policy.json`:

- a **default section template** the user can edit (default sections: Decisions /
  Changes / Open Questions / Next Steps), with on/off toggles;
- plus a **free-text steer** for emphasis (e.g. "focus on architectural decisions,
  skip dependency bumps").

The note author (agent or backend) reads the policy as guidance each session.

`/brain2:notes` modes:

- **show** — print the current policy.
- **quick edit** — set the free-text steer / toggle sections inline.
- **`--wizard`** — a **HITL loop**: the agent brainstorms the policy with the user,
  asking **one multiple-choice question at a time** (mirrors
  `_shared/kg-schema-wizard.md`), co-designing the template + steer. The result is
  written to `notes-policy.json` at a turn boundary — the user opts in; brain2 never
  blocks mid-flow.

## Surfaces

### Plugin skills (new + touched)

- `skills/notes/SKILL.md` — `/brain2:notes` — show / quick-edit / `--wizard`.
- `skills/docs/SKILL.md` — `/brain2:docs` — read/browse the curated tree;
  `--rebuild` forces a distill now.
- `_shared/notes-policy.md` — canonical policy shape + default template.
- `_shared/session-note.md` — the agent-rich note-writing convention the `Stop`
  hook invokes.

### Hooks (plugin `hooks/`)

- `SessionStart` → spawn the auto-capture background agent.
- `SessionEnd`/`Stop` → write the session note, then signal the debounced
  distill check.

### Backend

- snapshot→note fallback distiller;
- taxonomy-inference + doc-tree writer (a new `brain2/docs/` module);
- both best-effort, fail-silent. Reuses `embed_batch`, `insert_findings`, and the
  synopsis patterns. The doc-tree writer is the one piece that writes into the repo's
  `.brain2/` — local-tier writes directly; the agent-driven path keeps it
  tier-agnostic (the cloud backend cannot write the user's repo).

## Persistence

- **No new Store tables for v1.** Notes ride the existing Finding surface
  (`category="note"`). Doc-tree state (`notes-policy.json`, `docs-state.json`) is
  local on-disk JSON.

## Config gates (env, default-on, master kill-switches)

- `BRAIN2_LIVING_DOCS` — master switch for the whole feature.
- `BRAIN2_AUTO_CAPTURE` — auto-capture loop on/off.
- `BRAIN2_AUTO_CAPTURE_INTERVAL` — tick interval (default ~3 min).
- `BRAIN2_DISTILL_DEBOUNCE_N` / `BRAIN2_DISTILL_DEBOUNCE_T` — distill debounce
  thresholds.

## Build sequence

Each step is independently shippable and degrades to silence if disabled.

1. `.brain2/` layout + `notes-policy.json`/`docs-state.json` schemas + `.gitignore`
   write.
2. Note-as-Finding (`category="note"`) + agent-rich `Stop` hook +
   `_shared/session-note.md`.
3. `/brain2:notes` skill + wizard.
4. Auto-capture `SessionStart` agent (change-driven).
5. Backend fallback distiller (snapshots→note).
6. Distill loop: taxonomy inference + doc-tree writer + debounce.
7. `/brain2:docs` skill.

## Open questions / future

- Whether to promote the inferred taxonomy into a first-class doc-layout schema
  (vs reusing `KGSchema`).
- Cloud-tier doc-tree writing (today only local-tier / agent-driven writes into the
  repo `.brain2/`).
- Optional: surface the curated doc tree in the iOS companion read spine.
