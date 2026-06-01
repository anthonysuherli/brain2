# brain2 as a Personal Knowledge Engine — Synthesis/Distillation Design

**Date:** 2026-06-01
**Status:** Design (validated against current code)
**Supersedes/extends:** `2026-05-30-activity-kg-design.md` (this adds a third node tier on top of the activity KG)

## 1. Positioning

brain2 today is a **developer capture/resume engine**: per-repo+branch sessions
produce resume cards, and a web gap-fill pipeline (explore) seeds KBs. This design
repositions brain2 as a **personal knowledge engine**: one per-user graph that
**grows from two intake streams — your explorations/searches and your activity —
and then grounds any surface you're on with the right slice of what you know.**

The wedge is **synthesis/distillation**: brain2 doesn't just store what you read
and did, it **distills it upward into concepts** — higher-order claims that link
*what you did* to *what you learned*, get re-distilled as new evidence lands, and
lead every grounding card. Memory that compounds, not memory that accumulates.

Three properties define "personal knowledge engine" here:

- **Compounds** — raw findings + activity roll up into concepts; concepts re-distill
  as evidence arrives (reinforce / refine / contradict).
- **Cross-boundary** — concepts span KBs (repo+branch), so a synthesis can cite
  evidence from `repoA/dev` *and* `repoB/main`. This is the personal payoff.
- **Portable** — a single context endpoint returns your relevant knowledge slice
  given *where you are now*, so Claude Code grounds on it today and any other
  surface (iOS, other tools) taps the same slice later.

## 2. What this builds on (grounded in current code)

This is an **additive third tier on the existing activity KG**, not a new
subsystem. What already exists and is reused verbatim:

| Existing piece | Reused for |
|---|---|
| `knowledge_graph/` activity KG (`kg_nodes`/`kg_edges`/`vec_kg_nodes`, per-org, cross-repo) | Concepts are a new node **type** in this same graph |
| `KGNode.grounded_in: list[str]` (finding ids) | Concept→evidence link — **no need to make findings into nodes** |
| `match_kg_nodes` (semantic seed) + `get_kg_subgraph` (expand) | Concept retrieval + neighborhood selection for distillation |
| `schedule_activity_update` fire-and-forget hook (`api/capture.py:60`) | Where concept distillation is chained in |
| `exploration/evaluator.py` (batched critic) | Quality-gates synthesized concepts |
| `exploration/merger.py` (fuzzy cluster + blended confidence) | Concept dedup + confidence math |
| `agent/preamble.py` coverage banding (`band_findings`/`assess_coverage`) | Concepts become a tier **above** band-1 findings in the context card |
| `agent/synopsis.py` (per-KB topic rollup) | **Conceptually subsumed** — the synopsis is the cheap precursor of the concept tier |

The reserved per-org activity KB (`__activity__`/`default`, via
`resolve_activity_target`) is the home for concepts — they are personal-scoped by
construction.

## 3. Data model — the Concept tier

A **concept** is a `kg_nodes` row with `type='concept'`. No new table; we reuse the
graph so concepts dedupe, embed, and connect like every other node.

```
kg_nodes (type='concept')
  label        canonical one-line claim   (dedupe key + embedded text)
  grounded_in  [finding_id, …]            evidence (EXISTING field)
  properties   {
    body          synthesized prose (the distilled explanation)
    confidence    0..1   (blended: source agreement × critic quality)
    status        active | superseded | contested
    version       int    (bumped on re-distillation)
    superseded_by node_id | null
    source_kbs    [kb_id, …]   which sessions/KBs contributed
    updated_at    iso8601
  }
  embedding    claim embedding → vec_kg_nodes (semantic retrieval)
```

**Edges** (all `kg_edges`, reusing the existing relation field):

- `concept --refines--> concept` — a new version supersedes/sharpens an older one.
- `concept --contradicts--> concept` — flagged conflict (both kept, status `contested`).
- `concept --supports--> concept` — corroboration across domains.
- `concept --about--> {task|file|repo}` — **binds knowledge to activity**. This is
  the join that makes "understand your context anywhere" work: from the task you're
  on → the concepts about it → the findings that justify them.

**Why type-in-the-KG, not a separate `insights` table** (reversed from an earlier
draft): your stated vision is "it develops the KG." Concepts-as-nodes get
`match_kg_nodes`, `get_kg_subgraph`, the per-org RLS scoping, and the cross-repo
home for free, and they connect to activity nodes with ordinary edges. A separate
table would re-implement all of that and sit *outside* the graph you want to grow.

**Evidence via `grounded_in`, not finding-nodes** — findings stay KB-scoped rows;
concepts reference them by id in the existing `grounded_in` field, exactly as
activity nodes already do. Retrieval joins finding rows on demand.

## 4. The distillation pipeline

Mirrors the exploration pipeline's shape (`plan → … → evaluate → merge`) but over
*internal* evidence instead of the web. Lives in `knowledge_graph/distill.py`.

```
neighborhood select ─► synthesize (LLM) ─► evaluate (critic) ─► reconcile ─► upsert
```

1. **Neighborhood select** — given a trigger (a new finding, a freshly-explored
   batch, or an explicit topic), gather the relevant evidence cluster:
   - semantic: `match_findings` / `match_kg_nodes` around the trigger text;
   - structural: findings `grounded_in` the touched task/files (via `get_kg_subgraph`).
   Cap by count + recency (config `distill_neighborhood_cap`).

2. **Synthesize** — one structured LLM call (`structured_completion`, Sonnet 4.6,
   same client the planner/evaluator use) over the evidence cluster → candidate
   concept(s) `{claim, body, evidence: [finding_id], related_claims}`. Prompt
   forbids vacuous claims (same discipline as the planner's extraction prompt).

3. **Evaluate** — reuse `evaluate_findings`-style batched critic: score each
   candidate concept's signal quality in [0,1], drop non-concepts. Gated by
   `BRAIN2_DISTILL_LLM`; best-effort.

4. **Reconcile** — the compounding step. For each surviving candidate, find the
   nearest existing concept by `match_kg_nodes` (cosine ≥ `reconcile_min_sim`) +
   fuzzy claim match (`merger._similar`, ≥0.80):
   - **no match** → new concept node.
   - **match, consistent** → *reinforce*: union evidence into `grounded_in`, bump
     confidence via `blended_confidence(source_count, quality)`, bump `version`,
     refresh `body`. Requires `update_kg_node` (see §7).
   - **match, conflicting** (LLM judges the new claim contradicts the old) → write a
     `contradicts` edge, set both `status='contested'`; do not silently overwrite.
   - **match, strictly better** → new node + `refines` edge, old node
     `status='superseded'`, `superseded_by` set.

5. **Bind to activity** — write `about` edges from the concept to the task/file/repo
   nodes its evidence is `grounded_in`, so the concept is reachable from where you work.

Confidence reuses `merger.blended_confidence` (source count × critic quality), so a
multi-session, multi-source concept outranks a one-off — the same curve findings use.

## 5. Triggers

Distillation is **best-effort and fire-and-forget**, identical discipline to the
activity KG (a failure never breaks a capture or an explore).

- **On capture** — chain after `schedule_activity_update` in `api/capture.py`: once
  the snapshot's activity nodes exist, distill the touched neighborhood. Debounced
  by a delta counter (like `synopsis.should_rebuild`): only distill when ≥N new
  findings have landed in the neighborhood, so every keystroke-capture doesn't fire
  an LLM pass.
- **On explore completion** — after `run_exploration` persists findings
  (`api/explore.py`), distill over the freshly-added batch — web learning compounds
  immediately.
- **Explicit** — `/brain2:distill [topic]` / `brain2_distill` forces a pass over a
  topic or the whole recent neighborhood (the synchronous, user-driven path).

Master gate `BRAIN2_DISTILL_KG` (default on); LLM sub-gate `BRAIN2_DISTILL_LLM`
(default on; off = no synthesis, pipeline no-ops). Mirrors
`BRAIN2_ACTIVITY_KG` / `BRAIN2_ACTIVITY_LLM`.

## 6. Retrieval — the context-anywhere surface

The payoff. Generalize the KB-scoped preamble into a **person-scoped, location-aware
context packet**.

**New endpoint** `GET /v1/context` and MCP tool `brain2_context`:

```
input:  where you are  — {project, kb}  OR  free-text "what am I doing"
output: a banded context card:
  concepts:  top distilled concepts for this location/intent   (NEW top tier)
  evidence:  supporting findings beneath the concepts          (band-1/2/3)
  activity:  recent linked sessions/tasks (the existing rollup)
  coverage:  rich | sparse | gap
```

**How it assembles:**
- Embed the intent (location text or query).
- `match_kg_nodes(type='concept')` → seed concepts; `get_kg_subgraph` expands to the
  `about`-linked tasks/files and `grounded_in` findings.
- `match_findings` (existing) fills the evidence tier.
- **Banding extends one tier up**: concepts sit above band-1. The existing
  `band_findings`/`assess_coverage` heuristic is reused for the evidence tier; a new
  thin `band_concepts` (same cosine thresholds) sizes the concept tier.
  `render_preamble` gains a `<concepts>` block rendered *before* `<findings>`.

This means **grounding leads with distilled understanding, then evidence** — and
because concepts are cross-KB, the card surfaces relevant knowledge from *other*
repos when it bears on what you're doing now. `/brain2:resume` and `/brain2:search`
re-point at this assembler; the KB-scoped preamble becomes a special case (location
= one KB).

## 7. Store protocol changes

Minimal — one new write primitive, one optional read:

- **`update_kg_node(kb_id, node_id, *, properties, grounded_in, embedding) -> None`**
  *(new, required)* — replace a node's payload. Needed because `upsert_kg_nodes`
  merges properties with `setdefault` (never overwrites), which is correct for
  append-only activity nodes but wrong for a re-distilled concept `body`/`confidence`.
  Implement on both `SQLiteStore` (UPDATE + vec re-insert) and `SupabaseStore`.
- **`list_kg_nodes(type='concept', …)`** *(exists)* — reused for the concept list
  read; no change.

No schema migration: `kg_nodes`/`kg_edges`/`vec_kg_nodes` already hold everything.
Cloud RLS: concepts are `kg_nodes` rows, already org-scoped by the multi-user auth
work — no new policy.

## 8. Surfaces

| Surface | Change |
|---|---|
| `brain2_context` (MCP) + `GET /v1/context` | **New** — the portable grounding packet (§6) |
| `brain2_distill` (MCP) + `POST /v1/distill` | **New** — force a distillation pass |
| `/brain2:distill` skill | **New** — `skills/distill/SKILL.md` |
| `/brain2:resume`, `/brain2:search` | Re-point at the context assembler (concepts lead) |
| `GET /v1/activity/graph` | Concepts appear as nodes; no API change |
| iOS app | Future read: concept tier on the resume card (out of scope here) |

## 9. Build order (vertical slices)

**Phase A — Concept tier + write path.** Add `update_kg_node` to the Store
protocol (both tiers). Add `knowledge_graph/distill.py` with synthesize + reconcile.
No triggers yet — drive it from a test/CLI. *Done when:* a manual call over a KB's
findings produces `concept` nodes with evidence + `about` edges.

**Phase B — Triggers.** Chain distillation off capture + explore (debounced,
gated). *Done when:* working normally for a session grows the concept tier
automatically, and a failure is logged but never breaks capture/explore.

**Phase C — Context endpoint.** `band_concepts` + `<concepts>` in `render_preamble`;
`/v1/context` + `brain2_context`; re-point resume/search. *Done when:*
`brain2_context` returns concepts-over-evidence and surfaces a cross-KB concept when
relevant.

**Phase D — Explicit surface.** `/brain2:distill` skill + `brain2_distill`.

Each phase is independently shippable and best-effort, so the engine degrades to
today's behavior if any phase is gated off.

## 10. Risks & mitigations

- **`kg_nodes` was built for exact-dedupe structural nodes; concepts are mutable +
  versioned.** Mitigation: `update_kg_node` + payload-held version/status; keep the
  *label* (dedupe key) stable across versions by keying concepts on a canonical
  claim and letting `body` mutate. Watch for label drift splitting a concept into
  duplicates.
- **Distillation quality is an LLM-judgment problem.** Without firm critic gating
  the concept tier becomes vague-claim noise that pollutes every context card.
  Mitigation: reuse the evaluator critic, reserve high confidence for dense
  multi-source concepts, and keep `BRAIN2_DISTILL_LLM` as a kill switch.
- **Reconciliation thrash** (a concept flip-flopping active↔superseded across runs).
  Mitigation: require the LLM's supersede/contradict verdict to clear a margin, and
  debounce re-distillation by the same delta counter as synopsis.
- **Cost** — synthesis is an extra LLM pass per trigger. Mitigation: debounce
  (delta-gated), batch the neighborhood into one call, and keep it off the request
  path (fire-and-forget).
- **Cross-KB scoping bug = privacy leak** (one user's concepts citing another's
  findings). Mitigation: concepts live in the per-org reserved KB; reuse the
  existing org-scoped RLS path — no service-client reads.

## 11. YAGNI — explicitly deferred

Not in this design; revisit only after the grow→ground loop is proven:

- Cross-domain ingestion (browser history, notes, chats, papers) — prove the loop on
  the two intake streams (explore + capture) that already exist first.
- Spaced resurfacing / decay scheduling — a read-time concern, not a model concern.
- Contradiction-resolution UI — store `contested` status now; surface/resolve later.
- Multi-device sync, team-shared concepts — cloud value props, separate track.
- Replacing the synopsis — leave it running; concepts subsume it gradually.

## 12. Open question for review

The concept **dedupe key is the `label` (canonical claim)**. Two phrasings of the
same idea won't exact-match, so reconciliation leans on semantic+fuzzy matching at
*write* time to find the right node to update. If that proves too leaky (duplicate
concepts), the fallback is a content-hash or an explicit `concept_key` in
properties. Flagged because it's the one place the reused `(kb_id, type, label)`
dedupe model is stretched.
