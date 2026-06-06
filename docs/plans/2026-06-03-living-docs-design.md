# br8n Living Docs — design

**Date:** 2026-06-03
**Status:** Design (validated via brainstorming; not yet implemented)
**Working name:** Living Docs

## Summary

br8n grows a third memory surface alongside snapshots and the activity-KG: a
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
- a rendered markdown file at `.br8n/notes/<kb>/<timestamp>-<slug>.md`.

Notes are **append-only** — a faithful journal of what happened, never rewritten.

**Layer 2 — Curated doc tree (the synthesis).** A deduped, organized knowledge base
distilled *from* the note-Findings into `.br8n/docs/…`. These files are **rendered
output only — never re-ingested as Findings**. (Re-ingesting would create a
distill-its-own-output drift loop where each pass re-distills its own synthesis.) The
KB is the source of truth; the doc tree is the maintained view.

## On-disk layout

All under repo-root `.br8n/`, **git-ignored** (a per-developer working set,
co-located with code for easy reading, never committed — no PR noise):

```
.br8n/
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

### 1. Auto-capture loop — CC-session-scoped, **drift-triggered**

- A **`SessionStart` hook** launches a non-LLM watcher subprocess that lives for the
  Claude Code session and dies on `SessionEnd` (stop-file signalled by a `SessionEnd`
  hook).
- Each tick (default ~3 min, `BR8N_AUTO_CAPTURE_INTERVAL`): read git state, then
  compute **drift vs the last persisted snapshot** using the *same definition the
  statusline renders* — `moved` (tracked files changed now vs the files the snapshot
  recorded, via `git diff HEAD --name-only`) and `commits` (commits on HEAD since the
  snapshot's timestamp).
- **Capture when drifted** — i.e. `moved >= DRIFT_FILES_WARN (2)` **OR** `commits >= 1`
  — or when there is no prior snapshot (first anchor). Otherwise no-op. Each capture
  resets the baseline, so cadence is self-bounded (no tiny near-duplicate snapshots).
- **Carry forward the last hypothesis.** Auto-captures have no fresh human intent, so
  they reuse the most recent hypothesis for this repo+branch (intent persists across
  small drifts) rather than recording a blank one. `trigger="idle"`.
- **Commit = instant re-anchor.** A best-effort `post-commit` git hook (installed into
  `<repo>/.git/hooks/`, marker-guarded + append-safe) fires a one-shot capture the
  moment a commit lands — the strongest drift signal — on top of the poll.
- **One drift definition, two consumers.** The threshold + algorithm live in
  `br8n/livingdocs/drift.py`; the watcher imports it, and the statusline
  (`scripts/br8n-statusline.py`, a zero-dependency script) keeps an in-sync copy.
  The statusline *shows* "drifted"; the watcher *acts* on it. (Distinct from
  `knowledge_graph/drift.py`, which is KG-schema drift — unrelated.)
- Restores the always-on journal lost when the VS Code extension was removed. No
  daemon, tier-agnostic, no duplicate-snapshot noise.

### 2. Session-note write — once per conversation

A **`Stop`/`SessionEnd` hook** fires the note author:

- **Agent-rich path:** the CC agent, still holding the full conversation in context,
  writes the note per the KB's `notes-policy.json` (template + steer) → persists a
  `note` Finding *and* writes the `.br8n/notes/<kb>/…` file. Best quality —
  captures decisions and reasoning, not just structural diffs.
- **Backend-fallback path:** if no agent note exists for the session (e.g. capture
  came from another surface), the backend distills a thinner note from the session's
  snapshots — same shape, lower confidence.

This is the **hybrid** model: agent-rich when a session ran through CC, backend
fallback otherwise. Best coverage; two code paths.

### 3. Distill loop — debounced, after notes land

A **background agent** re-distills the curated tree when `N` new notes
(`BR8N_DISTILL_DEBOUNCE_N`) **or** `T` elapsed (`BR8N_DISTILL_DEBOUNCE_T`) since
the last run (tracked in `docs-state.json`). It:

- reads note-Findings,
- updates the inferred taxonomy (or honors the user schema),
- writes/moves **only affected files** under `.br8n/docs/`,
- **never re-ingests its output.**

Debouncing keeps it from running every session and bounds cost/file churn; a full
taxonomy reshuffle happens only occasionally. `/br8n:docs --rebuild` is the
on-demand escape hatch.

## Note policy — template + free-text steer, with a wizard

The user dictates "what kind of notes get taken" per repo+branch via
`notes-policy.json`:

- a **default section template** the user can edit (default sections: Decisions /
  Changes / Open Questions / Next Steps), with on/off toggles;
- plus a **free-text steer** for emphasis (e.g. "focus on architectural decisions,
  skip dependency bumps").

The note author (agent or backend) reads the policy as guidance each session.

`/br8n:notes` modes:

- **show** — print the current policy.
- **quick edit** — set the free-text steer / toggle sections inline.
- **`--wizard`** — a **HITL loop**: the agent brainstorms the policy with the user,
  asking **one multiple-choice question at a time** (mirrors
  `_shared/kg-schema-wizard.md`), co-designing the template + steer. The result is
  written to `notes-policy.json` at a turn boundary — the user opts in; br8n never
  blocks mid-flow.

## Surfaces

### Plugin skills (new + touched)

- `skills/notes/SKILL.md` — `/br8n:notes` — show / quick-edit / `--wizard`.
- `skills/docs/SKILL.md` — `/br8n:docs` — read/browse the curated tree;
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
- taxonomy-inference + doc-tree writer (a new `br8n/docs/` module);
- both best-effort, fail-silent. Reuses `embed_batch`, `insert_findings`, and the
  synopsis patterns. The doc-tree writer is the one piece that writes into the repo's
  `.br8n/` — local-tier writes directly; the agent-driven path keeps it
  tier-agnostic (the cloud backend cannot write the user's repo).

## Persistence

- **No new Store tables for v1.** Notes ride the existing Finding surface
  (`category="note"`). Doc-tree state (`notes-policy.json`, `docs-state.json`) is
  local on-disk JSON.

## Config gates (env, default-on, master kill-switches)

- `BR8N_LIVING_DOCS` — master switch for the whole feature.
- `BR8N_AUTO_CAPTURE` — auto-capture loop on/off.
- `BR8N_AUTO_CAPTURE_INTERVAL` — tick interval (default ~3 min).
- `BR8N_DISTILL_DEBOUNCE_N` / `BR8N_DISTILL_DEBOUNCE_T` — distill debounce
  thresholds.

## Build sequence

Each step is independently shippable and degrades to silence if disabled.

1. `.br8n/` layout + `notes-policy.json`/`docs-state.json` schemas + `.gitignore`
   write.
2. Note-as-Finding (`category="note"`) + agent-rich `Stop` hook +
   `_shared/session-note.md`.
3. `/br8n:notes` skill + wizard.
4. Auto-capture `SessionStart` agent (change-driven).
5. Backend fallback distiller (snapshots→note).
6. Distill loop: taxonomy inference + doc-tree writer + debounce.
7. `/br8n:docs` skill.

## Open questions / future

- Whether to promote the inferred taxonomy into a first-class doc-layout schema
  (vs reusing `KGSchema`).
- Cloud-tier doc-tree writing (today only local-tier / agent-driven writes into the
  repo `.br8n/`).
- Optional: surface the curated doc tree in the iOS companion read spine.
