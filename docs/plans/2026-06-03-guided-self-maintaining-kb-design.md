# brain2 — Guided, Self-Maintaining, Portable Personal KB — design

**Date:** 2026-06-03
**Status:** Design (validated via brainstorming) — **implemented.** Detector +
offer-computation + guided wizard SKILL shipped in `2c2961a`; the turn-boundary
surfacing hook (D4) + `/brain2:schema` manifest registration added on `dev`. See §10
for the as-built reconciliation. Remaining open item: D2 (windowed drift ratio).
**Working name:** Guided KB / schema-drift loop
**Relationship:** Umbrella positioning over `2026-06-01-personal-knowledge-engine-design.md`
(concept tier + portable context) and `2026-06-03-living-docs-design.md` (background
auto-capture + distill-in-flight). Adds the one new mechanic those two lack: a
**drift detector → gated, guided schema-(re)design loop.**

## 1. Positioning (the umbrella)

**One-liner:** *brain2 — a self-maintaining, portable personal knowledge base you
manage agentically, guided at the one seam that matters: its schema.*

brain2 watches you work, distills what it learns into one personal graph, and keeps it
organized in the background — across every repo and machine. You never hand-edit nodes
or write schema files; you operate it by conversation. It stays silent until the *one*
moment a human decision is genuinely required: when the shape of your knowledge — its
ontology — needs to change.

Five properties, each backed by machinery that already exists or is designed; unified
by one new piece:

| Property | What delivers it | Status |
|---|---|---|
| **Self-maintaining** | Background loops: auto-capture subagent → notes → distill-to-concepts → doc tree. Memory that compounds, not accumulates. | designed (living-docs, personal-knowledge-engine) |
| **Portable** | brain2-the-cloud is the provider: your per-user graph + concepts sync across workspaces & machines, so context follows you from `repoA`/laptop to `repoB`/desktop. | north-star (cloud sync listed *future* in CLAUDE.md) |
| **Non-blocking** | Core philosophy — all of it runs *around* your turn, fails silent, never modal mid-flow. | shipped |
| **Agentically-managed** | Every operation on the KB — grow, query, reshape, curate — is performed by an agent on your behalf from natural-language intent. No manual data-wrangling. | shipped (plugin skills + MCP tools) |
| **Guided** | **← this design.** The system is silent by default; the one time it seeks you out is when the KG ontology no longer fits what you're accumulating — a turn-boundary offer to (re)design the schema. | **new** |

**Thesis:** a self-maintaining system needs exactly **one** human-in-the-loop seam —
the schema. Everything else is inference brain2 does alone. "Guided" is not a constant
co-pilot; it is a *rare, well-timed tap on the shoulder* when the **structure** of your
knowledge (not its content) needs a human decision. The drift detector earns the right
to that tap by firing only when it is genuinely warranted.

## 2. The drift detector

**Schema target:** the **KG ontology** (the activity/concept knowledge-graph's node &
edge types — `KGSchema`). Drift = the entities/relations you're accumulating no longer
fit the seeded activity ontology. (Doc-tree taxonomy and note-policy are *not* the
target here — see §7.)

The one-liner names **two triggers**, treated as two modes of one detector:

- **Cold-start** ("enough context is collected") — no schema designed yet, and enough
  signal has piled up to propose a first one. *Volume-driven.*
- **Drift** ("have drifted") — a schema exists but reality moved past it.
  *Misfit-driven.*

### Signal — extraction residual (free-rides on work already happening)

The activity extractor already runs fire-and-forget on every capture
(`schedule_activity_update`, `api/capture.py`). Each extracted entity gets a type from
the ontology + a confidence. The detector reads the **residual** off that pass — **no
new trigger, no extra LLM call.**

An extracted node is flagged `residual` if **any** of:

- it landed in the catch-all / generic type (the extractor couldn't place it), **or**
- its extractor-reported type confidence `< τ_fit`, **or**
- its label's max cosine to the existing type exemplars `< τ_sim`.

The flagged nodes are **not noise to discard — they are the proposal seed.** What does
not fit the ontology *is* what the ontology is missing.

### Bookkeeping — one ledger, count-based window

A per-user `schema-state.json` (mirrors living-docs' `docs-state.json`):

```
schema-state.json
  schema_version       int
  last_design_at       iso8601
  nodes_since_design   int                    # cold-start counter
  window               [bool, …]              # last W residual flags (count-based)
  residual_seed        [node_id, …]           # the misfit cluster to hand the loop
  last_offer_at        iso8601 | null
  offer_status         pending | offered | accepted | declined
  declined_at_residual int | null             # for re-arm (see §3)
```

The window is **count-based** (`last W extractions`), not time-based — capture cadence
is bursty, so N events is a steadier denominator than N minutes.

### Fire conditions

- **Cold-start** — `schema_version == 0` **and** `nodes_since_design ≥ N_min`.
- **Drift** — `schema_version > 0` **and** residual-ratio over the last `W`
  extractions `≥ ρ` **and** absolute residual count `≥ floor` (so a 3-node window
  can't trip it).

Either way the detector only **raises a flag** + bundles `residual_seed`. It never
reshapes anything itself — that is the gated offer (§3).

## 3. The gated offer (the one tap on the shoulder)

A raised flag is **latent** — it does nothing until a turn boundary (non-blocking by
default). Path: **detection (background) → flag in `schema-state.json` → offer (turn
boundary).**

A `SessionStart` hook reads the ledger; if a flag is `pending` and not recently
offered, it emits **one line** — fired at `SessionStart` (you're between tasks,
receptive), not `Stop` (you're mid-flow, leaving):

- cold-start: *"brain2 has collected enough to propose a knowledge schema — design it?
  `/brain2:schema`"*
- drift: *"Your activity no longer fits its schema (12 unplaced entities around
  'deployment', 'incidents') — reshape it? `/brain2:schema`"*

The drift offer **names the residual cluster** — it tells you *what* drifted, so the
offer is legible, not a vague nag. That naming is free from `residual_seed`.

**Offer once, then go quiet (anti-nag contract).** On surfacing, stamp `last_offer_at`
+ set `offer_status`:

- **accepted** → run the loop (§4), reset counters, bump `schema_version`.
- **declined / ignored** → stamp and **stop re-raising every launch.** The capability
  stays available on demand (`/brain2:schema` always works).

**Re-arm without nagging:** a declined drift offer re-arms only after the residual count
grows by a further `Δ_rearm` beyond `declined_at_residual` — so if drift keeps
intensifying it can eventually re-ask, but steady-state "I said no" stays quiet. This is
the "stamp it and move on" rule with a pressure-release valve.

## 4. The guided schema loop (the agentic management action)

Accepting the offer (or running `/brain2:schema` cold) launches a **HITL co-design** —
the one place brain2 trades silence for dialogue. This **reintroduces delapan's
`propose_schema` + `kg-schema-wizard`** (currently excluded from the brain2 fork per
CLAUDE.md), now **drift-seeded** rather than blank-slate.

**Inputs the agent reads:** current `KGSchema` (empty on cold-start) + the
`residual_seed` cluster + a recent node sample. The seed is the gift: the agent isn't
asking "what should your ontology be?" from nothing — it's saying "here are 12 things
that didn't fit, clustered into 2 shapes; let's name them."

**The loop (one question at a time, mirrors `_shared/kg-schema-wizard.md`):**

1. `propose_schema` drafts a candidate **delta** — new node types, new edge types,
   merges/renames — grounded in the residual cluster.
2. Wizard presents it as **single multiple-choice questions**: *"A cluster around
   deploys & rollbacks doesn't fit — add a `Deployment` node type linked
   `caused→ Incident`? [add / refine / skip]"*
3. You steer; the agent revises. Co-design, never auto-apply.
4. On finish: persist the updated `KGSchema` (per-user — the activity graph is
   org-scoped), bump `schema_version`, reset the detector's counters.

**Agentic, end to end:** propose (agent) → steer (you, in dialogue) → apply (agent).
You never touch a schema file.

## 5. After the loop — apply, re-type, portability

**What happens to nodes extracted under the old schema:** apply the new schema **going
forward**, plus a **bounded re-type of just the `residual_seed` cluster** that motivated
the change (small, already in hand). A *full* graph backfill / re-extraction is **YAGNI
for v1** — flagged future. This keeps the accept cheap and the win immediate: the things
that didn't fit now do.

**Portability tie-in.** The schema is per-user and lives with the per-org activity KB,
so on the cloud tier a schema designed on one machine governs extraction on every other
— the ontology, not just the data, is portable. (Cloud sync itself remains the
designed-but-future value prop; this design assumes the local tier and the
agent-driven path, which is tier-agnostic.)

**Agentic-management framing.** The drift loop is simply the **highest-stakes** entry
in the agentic-management table — the one operation where the agent pauses for your
judgment before acting, because structure is the one thing it shouldn't decide alone:

| Management action | Agentic surface |
|---|---|
| Grow it | auto-capture subagent + `/brain2:capture`, `/brain2:explore` |
| Query it | `/brain2:search`, `/brain2:activity`, `/brain2:resume`, `/brain2:context` |
| **Reshape it** | **`/brain2:schema` — the drift-triggered guided loop (this design)** |
| Curate it | `/brain2:notes` wizard, `/brain2:docs` |

## 6. Surfaces, config, build order

### Surfaces

| Surface | Change |
|---|---|
| `/brain2:schema` skill (`skills/schema/SKILL.md`) | **New** — runs the guided loop; `--rebuild` forces a pass on demand |
| `_shared/kg-schema-wizard.md` | **Reintroduced** from delapan — the one-question-at-a-time convention |
| `brain2_schema` (MCP) + `POST /v1/schema/propose` | **New** — propose a schema delta from a seed |
| `knowledge_graph/schema.py` | **Reintroduced** — `propose_schema` machinery (ported, imports renamed) |
| `knowledge_graph/drift.py` | **New** — residual flagging + ledger update, chained off the extractor |
| `SessionStart` hook (plugin `hooks/`) | **New/extended** — read ledger, emit the gated one-line offer |
| `Store` | `KGSchema` read/write per-user (reuse existing node/edge surface; schema as a small per-org record) |

### Config gates (env, default-on, master kill-switches)

- `BRAIN2_SCHEMA_DRIFT` — master switch for the detector + offer.
- `BRAIN2_DRIFT_TAU_FIT` / `BRAIN2_DRIFT_TAU_SIM` — residual thresholds.
- `BRAIN2_DRIFT_WINDOW` (`W`), `BRAIN2_DRIFT_RATIO` (`ρ`), `BRAIN2_DRIFT_FLOOR`.
- `BRAIN2_SCHEMA_COLDSTART_N` (`N_min`), `BRAIN2_SCHEMA_REARM_DELTA` (`Δ_rearm`).

Mirrors the `BRAIN2_ACTIVITY_KG` / `BRAIN2_ACTIVITY_LLM` gating discipline. Best-effort:
a detector or offer failure degrades to "do nothing visible" and never breaks a capture.

### Build sequence (each step independently shippable, degrades to silence)

1. `schema-state.json` schema + ledger read/write + `.gitignore`.
2. `knowledge_graph/drift.py`: residual flagging chained off the extractor; update the
   ledger. No offer yet — assert via test/CLI that residuals accumulate.
3. Reintroduce `knowledge_graph/schema.py` (`propose_schema`) + `KGSchema` persistence.
4. `/brain2:schema` skill + `brain2_schema` + `_shared/kg-schema-wizard.md` — the
   guided loop, runnable on demand.
5. `SessionStart` hook: the gated, once-then-quiet offer (both modes).
6. Bounded re-type of the residual seed on accept.

## 7. Relationship to the other two designs (no conflict)

- **personal-knowledge-engine** owns the **concept tier** and the **portable
  `/v1/context`** assembler. This design does **not** touch distillation; it governs the
  *ontology* the concepts and activity nodes are typed against.
- **living-docs** owns the **background auto-capture loop**, the **session-note
  journal**, and the **doc-tree taxonomy**. The drift detector here is the
  **KG-ontology** analogue of living-docs' passive taxonomy inference — but *active*
  (it raises a gated offer) and pointed at the **graph schema**, not the on-disk folder
  layout. The two taxonomies stay separate: doc-tree layout is rendered output;
  KG ontology is the typed spine of the graph.

If both ever want one unified "knowledge schema," that is a future consolidation
(see open questions) — explicitly **not** v1, to avoid the over-coupling the YAGNI
sections of both parent designs warn against.

## 8. Risks & mitigations

- **Residual thresholds are guesses.** Too low → nags; too high → never fires.
  Mitigation: all of `τ_fit`, `τ_sim`, `ρ`, `W`, `N_min` are env-tunable; ship
  conservative (rather nag-never than nag-often) and tune from the ledger.
- **A bad schema proposal pollutes all downstream typing.** Mitigation: it's HITL —
  nothing applies without your `add/refine/skip` per question; `skip` is always free.
- **Reintroducing `propose_schema` risks a cross-repo dep.** Mitigation: port the file
  and rename imports `delapan.* → brain2.*`, exactly as the rest of the fork (CLAUDE.md
  convention). No runtime dependency on delapan.
- **Re-arm could still nag if drift oscillates around `Δ_rearm`.** Mitigation:
  re-arm compares against `declined_at_residual` (a high-water mark), so oscillation
  below the prior decline never re-fires.

## 9. Open questions / future

- Promote the KG ontology + doc-tree taxonomy + note-policy into a single first-class
  "knowledge schema" with one drift signal (the "all three, unified" option, deferred).
- Full graph backfill / re-extraction under a new schema (v1 does going-forward +
  residual-seed re-type only).
- Cloud-tier schema sync as a concrete feature (today: designed north-star).
- Whether the cold-start offer should also seed from `/brain2:explore` web findings,
  not just activity captures.

## 10. As-built reconciliation (commit `2c2961a`)

The detector, offer-computation, and guided wizard SKILL shipped in `2c2961a`
(`knowledge_graph/drift.py`, `brain2_schema_drift` MCP tool, `skills/schema/SKILL.md`,
`DriftConfig`, Store `get_kg_intent`/`set_kg_schema`, tests). Where it differs from
§§2–6 above, **the as-built is authoritative** for the items marked *adopt*:

| # | Design (§) | As-built | Resolution |
|---|---|---|---|
| **D1 signal** | residual = catch-all **OR** `conf<τ_fit` **OR** `cosine<τ_sim` (§2) | residual = type `"other"` **OR** off-schema type — type-only, free-rides on `kg_stats().by_type` | **Adopt as-built.** `τ_fit`/`τ_sim` dropped (no per-node confidence/embedding read needed). Cheaper, same intent. |
| **D2 window** | count-based last-`W` extractions (§2) | residual ratio over the **whole graph** (no window) | **Open.** As-built is conservative but dilutes recent drift as the graph grows. Revisit with a windowed/recency-weighted denominator once graphs are large; behind config. |
| **D3 state** | on-disk `schema-state.json` ledger (§2) | Store-backed markers (`init_offered` stamp + `drift_marker` = residual at last offer); `assess_drift(...)` is a pure function over them | **Adopt as-built** — tier-agnostic + testable; supersedes the JSON-file ledger. |
| **D4 surfacing** | `SessionStart` hook auto-emits the offer at a turn boundary (§3) | **now built** (`hooks/first-run-init.py`): the existing-KB branch calls `pending_schema_offer` (mirrors `brain2_schema_drift` in-process) and injects `offer_line` only when `should_offer` — silent otherwise. Stamps via `mark_drift_offered`/`mark_init_offered`. `/brain2:schema` registered in `plugin.json`. | ✅ **Closed.** Computed in-process (not via a directive that forces a tool call every session), so a no-drift session stays fully silent — strictly more non-blocking. |
| **D5 proposal** | reintroduce delapan `propose_schema` backend fn (§4) | **both:** `knowledge_graph/schema.py` (`propose_schema`/`validate_schema`) *was* reintroduced **and** the wizard SKILL drives it agentically | **Matches design** (correction: the backend fn exists; an earlier note wrongly said it wasn't ported). The agentic wizard is the human-facing surface over it. |
| **D6 re-type** | bounded re-type of just the residual seed; full rebuild deferred (§5) | **full graph rebuild** under the new schema (`brain2_build_graph(use_schema=True, rebuild=True)`); "full-rebuild only — no incremental today" | **Adopt as-built**, with a caveat: full re-extraction is more thorough but costlier on large graphs. The bounded-re-type / incremental path becomes the future optimization (§9). |

**Implemented `DriftConfig` defaults:** `min_nodes=8`, `cold_start_min_nodes=12`,
`drift_ratio=0.30`, `drift_floor=4`, `rearm_delta=6`. (Supersedes the env-name list in
§6: no `τ_fit`/`τ_sim`, no `W`, per D1/D2.)

**Net:** the full loop now works end to end — the detector fires, the `SessionStart`
hook surfaces the gated offer at a turn boundary, and `/brain2:schema` runs the guided
wizard. The one remaining open item is D2 (the whole-graph drift ratio), a
known-conservative simplification to revisit with a windowed denominator once graphs
are large.
