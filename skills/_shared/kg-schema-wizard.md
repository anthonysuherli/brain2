# kg-schema-wizard  (co-design the KG's intent — a 5-stage grounding wizard)

Co-design the knowledge graph's **intent** — the target ontology — *with the user*,
before building. The graph is then built to that intent (soft guidance), not blind
free-form extraction. Adapted from the KG-create wizard: br8n grounds on a KB's
**findings** (not a codebase), so "reconnaissance" mines findings + the existing graph,
and "grounding" labels real **findings** instead of code constructs.

Five stages: **reconnaissance → interview → grounding → proposal → set + build.**
A short interview, not a form — ask **one thing at a time** via `AskUserQuestion`.

## Stage 0 — Preamble-first

Preflight per [`preamble-first.md`](preamble-first.md). Tap the KB on the topic.
**Guard:** the KB must have findings to mine — if coverage is a `gap` (empty KB),
stop and suggest running `/br8n:explore` to fill coverage gaps first.

**Mode select:** call `mcp__br8n__br8n_get_kg_schema(project, kb)`. If `intent`
is non-null, an approved schema already exists → run the **Reconfigure flow**
(bottom). Otherwise proceed to Stage 1.

## Stage 1 — Reconnaissance (silent — no user interaction)

Build internal context that drives the questions and grounding examples. Do **not**
print this; gather it:

1. `mcp__br8n__br8n_propose_kg_schema(project, kb)` → a DRAFT ontology grounded
   in the findings: `node_types` (name/description/examples, plus typed `attributes`
   and an optional `layer`), `relation_types`, `relation_validity`, and
   `competency_questions`. If it returns a `note` (empty KB), surface it and stop.
2. `mcp__br8n__br8n_kg_stats(project, kb)` → category distribution + confidence
   — which categories dominate, where the evidence is strong.
3. The `kg_context` from the Stage-0 tap → most-connected entities + key relations
   (if a graph already exists), and the draft's `emergent` types if present.
4. Pick **3–5 "hot" findings** to use as grounding examples in Stage 3: highest
   confidence first, then most-connected / most-central to the synopsis spine. Use
   `mcp__br8n__br8n_resume` to surface the preamble and hot findings, or work
   from the findings returned in the propose output.

## Stage 2 — Guided interview (2–3 questions, one at a time)

**Lead with the competency questions.** Show the draft CQs and ask which actually
matter and what's missing — *"what should this graph let you answer?"* Then ask 1–2
more, derived from the recon signals (not generic), e.g.:
- *"Which kinds of things in this KB matter most to track as entities?"* — options
  drawn from the draft `node_types` + dominant categories.
- *"What relationship or dependency do you wish you could query but can't today?"* —
  options drawn from gaps in the draft `relation_types`.

Each as `AskUserQuestion` with 2–4 concrete options (each option a complete answer
with a one-line trade-off). Ask **one at a time**; wait for the answer before the
next. Keep an internal note of the user's vocabulary and the flows they describe.

## Stage 3 — Example grounding (the core — label real findings)

Anchor the abstract ontology in concrete findings the user personally types. For
each of the 3–5 hot findings from Stage 1:

1. Show its `title` + a ~3-line snippet of `content` (not the whole finding).
2. `AskUserQuestion`: *"What kind of thing is the central entity here?"* — offer 2–4
   suggested **node-type labels** drawn from the draft + Stage-2 answers, each option
   describing what that label implies for the graph (what it would connect to). The
   user can pick "Other" to coin their own.
3. Record the chosen label + the user's reasoning.

**Generalize.** After all examples: if the user gave several findings the same label,
propose it as a node type covering all such findings. If they described a connection
between two labels, capture it as a candidate relation. **Checkpoint** with
`AskUserQuestion`: *approve / adjust labels / add a missing type / redo grounding.*

## Stage 4 — Schema proposal (merge → approve loop)

Merge **interview CQs + grounded labels + the Stage-1 draft** into one intent schema:
- `node_types`: each grounded label → a class with `name` (short lowercase),
  `description`, `examples` (the real findings the user labeled), **`attributes`**
  (2–4 typed properties — `name` / `type` ∈ {text,number,date,url,list,bool} /
  `required` / `description`, drawn from what the findings report), and an optional
  **`layer`** grouping (cluster related classes; `""` if none).
- `relation_types`: verb-phrase classes from candidate relations.
- `relation_validity`: legal `source_type->target_type` pairs using your node-type
  names.
- `competency_questions`: the Stage-2 set.
- `regime`: `"soft"`.

Present the full schema — **lead with the CQs**, then the node types (showing each
class's attributes + layer), then relations + validity. `AskUserQuestion`:
*approve as-is / add types / remove types / modify (names, attributes, layer,
descriptions)*. Apply changes and re-present until approved. Echo the **final
schema** in full and get an explicit "yes, save it."

## Stage 5 — Set + build

1. `mcp__br8n__br8n_set_kg_schema(project, kb, schema)`. On
   `{ok: false, errors}` show the errors (e.g. an attribute with an unknown `type`,
   a dangling `relation_validity` pair), fix **with the user**, retry — nothing is
   saved until valid. On `{ok: true}` report the saved `version`.
2. Offer to build: run `mcp__br8n__br8n_build_graph(use_schema=True, rebuild=True)`
   — extraction is steered to the approved intent, fills each node's `properties` with
   the declared attributes + `layer`, and keeps out-of-schema signal as type `"other"`
   (never dropped).
3. After a build, `mcp__br8n__br8n_get_kg_schema(project, kb)` returns
   `{intent, emergent}` — compare to show how closely the built graph matches the
   intent, and whether the CQs are answerable. (Note: build is **full-rebuild only**
   today — no incremental.)

## Reconfigure flow (a schema already exists)

1. Load the current `intent` (Stage 0) — it's the starting point; preserve its CQs.
2. Run Stage 1 recon fresh.
3. **Present the delta** instead of Stage 2: which node/relation types are new in the
   draft, which look stale (no longer reflected in findings), what the emergent graph
   added. `AskUserQuestion`: *update (keep v_N, fold in the deltas) / start fresh
   (full 5-stage wizard).*
4. On **update**, run a shortened Stage 3 (ground only new/changed types), then
   Stages 4–5. `mcp__br8n__br8n_set_kg_schema` versions automatically; the build
   always uses the latest.

## Loop-back

See [`loop-back.md`](loop-back.md). The schema **is** the definition of "relevant"
every other op loops back against. If CQs aren't answerable after a build, that gap
cues `/br8n:explore` to fill coverage gaps.
