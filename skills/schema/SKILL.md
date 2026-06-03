---
name: schema
description: Design or reshape this repo+branch's knowledge-graph schema (its ontology) — the one human-in-the-loop seam of the self-maintaining KB. Use when the user wants to set up, review, or re-design the KG schema, when a drift offer was surfaced ("your graph has drifted… reshape it?"), or proactively to check whether the ontology still fits what's been collected. Calls brain2_schema_drift to decide cold-start vs drift, then runs the guided wizard.
---

# brain2 — Schema (the guided seam)

brain2 maintains itself silently; **structure** is the one thing it won't change
without you. This skill is that seam: it checks whether the KB's knowledge-graph
ontology still fits what's been collected, and — only when warranted — co-designs a
new one with you, one question at a time. Everything else (capture, distill, graph
population) happens in the background; here you *manage the shape*.

**Target** (same convention as every brain2 skill):
- `project` = current git repo name — `basename "$(git rev-parse --show-toplevel)"`
- `kb` = current git branch — `git rev-parse --abbrev-ref HEAD`

## Step 1 — Read the drift verdict

Call `mcp__plugin_brain2_brain2__brain2_schema_drift(project, kb)`. It reads the
built graph's type distribution against the approved schema (no LLM cost) and returns:

- `mode` — `cold_start` | `drift` | `ok` | `empty` (| `off` if the gate is disabled).
- `should_offer` — whether this is worth surfacing **now** (debounced; a declined
  offer doesn't re-nag until drift intensifies).
- `offer_line` — the ready-to-show one-liner (null unless `should_offer`).
- `residual` / `ratio` / `residual_types` — the off-ontology cluster: the entities
  the current schema couldn't place. **This is the seed** the wizard reshapes around.

**Route on `mode`:**

| mode | what it means | do |
|---|---|---|
| `empty` | graph too small to judge | tell the user there isn't enough yet; suggest `/brain2:capture` / `/brain2:explore`. Stop. |
| `ok` | the ontology still fits | report "schema v{n} still fits ({residual}/{node_count} unplaced)". Stop unless the user explicitly wants to reconfigure anyway. |
| `cold_start` | enough collected, no schema yet | go to Step 2 (first-run flow). |
| `drift` | schema set, reality moved past it | go to Step 2 (reconfigure flow), leading with the residual cluster. |

If the user invoked `/brain2:schema` **explicitly**, proceed to Step 2 even when
`should_offer` is false — the user opted in directly. If this skill was reached from
a **surfaced offer**, only proceed when the user accepts.

## Step 2 — Run the guided wizard

Hand off to [`_shared/kg-schema-wizard.md`](../_shared/kg-schema-wizard.md) — the
5-stage, one-question-at-a-time co-design loop. Two entry modes:

- **cold_start** → the full first-run flow (no schema exists).
- **drift** → the wizard's **Reconfigure flow** (a schema already exists). Seed
  Stage 1 with `residual_types` from Step 1 — these are exactly the unplaced clusters
  to name. Lead the delta with: *"these {residual} entities don't fit — mostly
  {residual_types}; let's place them."*

The wizard ends by calling `brain2_set_kg_schema` (versions automatically) and
offering `brain2_build_graph(use_schema=True, rebuild=True)`. The rebuild re-types
the residual cluster under the new ontology — so accepting visibly drops the
residual on the next drift check.

## Step 3 — Stamp the offer (debounce)

**Always**, right after surfacing a drift offer — whether or not the user accepted —
call `mcp__plugin_brain2_brain2__brain2_mark_drift_offered(project, kb, residual)`
with the `residual` from Step 1. This records the baseline so the offer won't
re-surface next session until drift grows past it (the "offer once, then go quiet"
contract). On **accept**, the rebuild already lowers residual; on **decline**, the
stamp is what keeps brain2 from nagging.

(No stamp needed for `cold_start` — that path debounces on the existing
`init_offered` first-run stamp.)

## Why this is the only seam

Capture, distillation, graph population, doc upkeep — all run as background agents
that never ask. Schema is the exception because the ontology defines what "relevant"
*means* for every other op; getting it wrong silently degrades everything downstream.
So brain2 stays quiet until drift earns the interruption, then asks **once**.
