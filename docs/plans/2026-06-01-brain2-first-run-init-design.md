# brain2 — First-Run Project Initialization + KG Schema Wizard

**Date:** 2026-06-01
**Status:** Design (validated via brainstorming)

## Summary

When a user opens a repo that brain2 has never seen, brain2 should **initialize
itself automatically**: a `SessionStart` hook detects the first run, Claude
dispatches a background subagent that seeds a repo-scoped KB from local context
(repo + git + project metadata) plus a small bounded web-enrichment pass, and —
once seeding completes — offers to set up the knowledge-graph schema by running
**Divergence's full 5-stage schema wizard**.

This is brain2's **first hook**. The plugin ships only skills today
(`resume`, `capture`, `search`, `explore`, `activity`) with no hooks and no
commands.

## Goals

- Zero-config first-run: opening a fresh repo seeds a useful KB without the user
  asking.
- Never block or hijack the user's first interaction — init runs in the
  background; the schema offer arrives at a turn boundary.
- Ground the KG schema in real, freshly-ingested findings so the wizard's draft
  ontology is repo-specific from the first question.
- Reuse Divergence's existing schema co-design wizard verbatim (substrate-adapted),
  not a bespoke shortcut.

## Non-goals (v1)

- Per-branch initialization. Init is **repo-scoped**; branches share the
  repo-level KB/schema. Per-branch session state (snapshots/resume) layers on top.
- Incremental KG build (Divergence's build is full-rebuild only today).
- Detect-and-resume of a half-finished init. A crashed init falls through to the
  existing `coverage='gap'` → `/brain2:explore` recovery path.
- Re-offering the schema setup on every launch. Offer **once**, then go quiet.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Launch model | Hook injects a first-run **directive**; Claude dispatches the init subagent (`Agent`, `run_in_background`). Keeps init in-conversation, orchestrated, interactive. |
| First-run detection | **KB existence = source of truth, repo-scoped.** No marker files; the KB itself is the state and the lock. |
| Init depth | **Local crawl + light web enrichment** (bounded Phase B). |
| Schema offer | Run **Divergence's full 5-stage wizard** (`divergence:graph schema`), multi-step `AskUserQuestion` co-design — not a one-click auto-set. |
| Offer timing | Announce one line on launch; **offer at the next turn boundary** when the background subagent completes. Never mid-edit, never blocking. |
| Re-offer policy | **Offer once**, stamp `init_offered_at`; then quiet. Wizard remains available on demand. |

## Architecture

### Trigger & first-run gate

A `SessionStart` hook (new `hooks` entry in `.claude-plugin/plugin.json`,
script under `skills/_shared/`) runs a fast guard on every session start:

- **Repo identity** = normalized git remote URL (fallback: repo-root path). Clones
  and worktrees of the same project resolve to the same identity; branches share it.
- The guard asks the brain2 backend a cheap `kb_exists`-style check (or reads a
  local cache the MCP server writes).
- **KB exists → emit nothing, exit 0.** Invisible on every subsequent launch.
- **No KB → first run.** Inject `additionalContext`: "This repo has no brain2 KB.
  Announce one line, then dispatch the brain2 init subagent in the background. Do
  not block the user."

Fails closed: not a git repo, no remote with no usable path, or backend
unreachable → exit silently. Never breaks a session. Critically, an *unreachable
backend* is treated as "can't determine" (emit nothing) — init fires only on a
confident "no KB exists," so we never double-seed on a false negative.

### Init subagent

One background subagent (`Agent`, `run_in_background`), two phases:

**Phase A — local crawl (free, deterministic, no network):**
- Repo structure — file/dir tree, languages, entry points, package manifests,
  build/test config.
- Git — recent log, active branches, top contributors, churn hotspots.
- Project metadata — README, CLAUDE.md/AGENTS.md, docs/, license.

Each becomes one or more **findings** via the existing capture/ingest path — same
finding shape the rest of brain2 reads. Creating the KB row is the **claim/lock**:
a concurrent second session's existence-check then sees "exists" and backs off.

**Phase B — light web enrichment (bounded):**
- Pick 2–4 high-value external facts surfaced by Phase A (main framework/runtime
  conventions, a couple of key dependency docs).
- Fire a **single bounded `brain2_explore` pass** with a small fixed query budget.
- If `brain2_explore` is unavailable or fails, skip — local findings still
  committed; the KB and schema offer proceed on local-only grounding.

**Output contract:** a compact structured result — KB identity, finding counts
(local vs web), draft-ready flag. As a background subagent, this surfaces to the
main loop as a tool-completion notification, not mid-edit.

### Schema offer — Divergence's 5-stage wizard (ported)

On subagent completion, Claude surfaces a one-line turn-boundary offer:
*"brain2 finished initializing this repo (N findings). Want to set up its
knowledge-graph schema?"* On **yes**, run the exact wizard from
`divergence/skills/graph/schema.md`, substrate-adapted (Divergence grounds on a
KB's findings; here the findings are the ones init just seeded):

1. **Reconnaissance (silent)** — `propose_kg_schema` → DRAFT ontology
   (`node_types` w/ attributes+layer, `relation_types`, `relation_validity`,
   `competency_questions`); `kb_stats` for category/confidence distribution; pick
   3–5 "hot" findings as grounding examples (entry points, churn hotspots, core
   framework).
2. **Guided interview (2–3 Q, one at a time)** — `AskUserQuestion`, lead with the
   competency questions (*"what should this graph let you answer about this
   repo?"*), then 1–2 recon-derived questions. 2–4 concrete options each.
3. **Example grounding** — per hot finding: title + ~3-line snippet,
   `AskUserQuestion` *"what kind of thing is the central entity here?"* with
   suggested node-type labels (+ "Other"). Generalize labels → node types,
   connections → candidate relations. Checkpoint.
4. **Proposal (merge → approve loop)** — merge CQs + grounded labels + draft into
   one intent schema (`regime: "soft"`). Present CQs first, then node types
   w/ attributes+layer, then relations+validity. Approve/add/remove/modify until
   explicit yes.
5. **Set + build** — `set_kg_schema` (fix validation errors with the user, retry),
   report version, offer the KG build.

### Edge cases

- **KB exists but empty** (prior init crashed mid-Phase-A): existence says
  "exists" → no auto-init. User hits `/brain2:resume` → `coverage='gap'` →
  `/brain2:explore` recovery. No half-init detection in v1.
- **User declines schema offer:** init findings stay (useful for resume/search);
  graph stays empty; wizard available later on demand. Stamp `init_offered_at` so
  we don't re-offer.
- **Concurrent sessions / double-fire:** KB-row creation is the atomic lock;
  second session sees "exists" and backs off.
- **Subagent fails mid-run:** partial findings persist; no offer (gated on
  structured success); next session sees KB exists → no re-init → gap/explore path.
- **Unanswered offer:** turn-boundary message, never blocking; scrolls away, no
  retry nagging.

## Components & file map

| Artifact | Type | Change |
|---|---|---|
| `skills/_shared/init-hook.py` (or `.sh`) | hook script | SessionStart guard: repo identity → `kb_exists` → inject directive or exit silent |
| `.claude-plugin/plugin.json` | manifest | add brain2's first `hooks` entry (SessionStart → guard) |
| `skills/_shared/project-init.md` | shared doc | init subagent brief: Phase A crawl → Phase B bounded web → seed findings → structured result |
| `skills/_shared/kg-schema-wizard.md` | shared doc | near-verbatim port of `divergence/skills/graph/schema.md` (5 stages), substrate-adapted to brain2 findings |
| brain2 MCP server | code | surface 4 tools from the Divergence fork: `propose_kg_schema`, `set_kg_schema`, `get_kg_schema`, `build_graph` |
| brain2 MCP server | code | cheap `kb_exists` check for the hook (or local cache the server writes) |
| KB row | data | add `init_offered_at` stamp (offer-once); KB existence is the first-run lock |

## Data flow (first run)

```
SessionStart hook → repo identity → kb_exists?
  ├─ yes → exit 0 (silent, every subsequent launch)
  └─ no  → inject directive
            → Claude: 1-line announce + dispatch background init subagent
                → Phase A: crawl repo/git/metadata → seed findings (claims KB row = lock)
                → Phase B: bounded brain2_explore (2–4 facts) → seed findings
                → return {kb, counts, draft-ready}
            → turn boundary: Claude offers schema setup (once; stamp init_offered_at)
                → yes → 5-stage wizard (recon → interview → grounding → proposal → set+build)
                → no  → findings stay; graph empty; wizard available later
```

## Build sequence (each step independently verifiable)

1. **MCP surface** — expose `propose_kg_schema` / `set_kg_schema` / `get_kg_schema`
   / `build_graph` + `kb_exists` in brain2's server. Verify via direct MCP calls.
   *(Unblocks everything; do first.)*
2. **`kg-schema-wizard.md`** — port the Divergence wizard, swap substrate language.
   Verify by running it by hand against an already-seeded brain2 KB.
3. **`project-init.md`** — the init subagent brief. Verify by dispatching it
   manually on a fresh repo; inspect seeded findings (Phase A, then Phase B).
4. **Hook + manifest** — SessionStart guard + `plugin.json` wiring. Verify: fresh
   repo triggers once; second launch silent; non-git repo silent; offer-once stamp
   respected.
5. **End-to-end** — fresh clone → launch → init → offer → wizard → built graph.

## Open dependency

brain2's MCP currently exposes only `capture`/`resume`/`explore`/`activity`.
None of the `*_kg_schema` tools nor a graph-build tool are surfaced. The backend
logic exists in the Divergence fork — the work is to surface it (step 1 above).
