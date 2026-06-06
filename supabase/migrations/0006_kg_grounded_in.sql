-- 0006_kg_grounded_in.sql — per-node/edge finding provenance for the KG.
--
--   extract_graph → grounded_in (LLM) → backfill_grounding (text-match) → kg_nodes/kg_edges
--
-- Each KG node and edge now records the finding ids that evidence it, so the graph
-- is auditable back to its source findings (and so coverage gaps — competency
-- questions with no grounded node — become detectable). Ported from delapan's
-- `grounded_in`. Stored as a jsonb array of finding-id strings (mirrors the
-- list[str] model and tolerates ids that no longer resolve). GIN-indexed for
-- containment queries ("which graph elements cite finding X?").

alter table kg_nodes add column grounded_in jsonb not null default '[]'::jsonb;
alter table kg_edges add column grounded_in jsonb not null default '[]'::jsonb;

create index idx_kg_nodes_grounded_in on kg_nodes using gin (grounded_in);
create index idx_kg_edges_grounded_in on kg_edges using gin (grounded_in);
