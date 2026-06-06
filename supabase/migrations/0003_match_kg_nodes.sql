-- =============================================================================
-- 0003 — match_kg_nodes: pgvector nearest-neighbour over kg_nodes.
-- Mirrors match_findings (0001); used by the KG builder to dedupe an
-- extracted entity against existing nodes before inserting a new one.
-- kg_nodes already carries `embedding vector(1536)` + an hnsw index (0001).
-- =============================================================================

create or replace function match_kg_nodes(
  query_embedding vector(1536),
  match_kb_id     uuid,
  match_count     int default 1,
  min_similarity  real default 0.0
)
returns table (
  id           uuid,
  type         text,
  label        text,
  properties   jsonb,
  similarity   real
)
language sql stable
as $$
  select
    n.id, n.type, n.label, n.properties,
    1 - (n.embedding <=> query_embedding) as similarity
  from kg_nodes n
  where n.kb_id = match_kb_id
    and n.embedding is not null
    and 1 - (n.embedding <=> query_embedding) >= min_similarity
  order by n.embedding <=> query_embedding
  limit match_count;
$$;
