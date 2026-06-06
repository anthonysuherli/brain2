-- -----------------------------------------------------------------------------
-- 0008: match_findings — org-wide + category-filtered search
-- Extends the 0001 RPC so kb_id may be null (search the whole org, scoped by
-- match_org_id) and an optional match_categories array filters by category.
-- Powers the journal's scope='both' recall across the journal + every KB's notes.
-- The arg list changes, so the old function is dropped first (create-or-replace
-- cannot alter a signature).
-- -----------------------------------------------------------------------------

drop function if exists match_findings(vector, uuid, int, real);

create or replace function match_findings(
  query_embedding  vector(1536),
  match_kb_id      uuid default null,
  match_count      int default 10,
  min_similarity   real default 0.0,
  match_org_id     uuid default null,
  match_categories text[] default null
)
returns table (
  id           uuid,
  title        text,
  content      text,
  category     text,
  confidence   real,
  tags         text[],
  provenance   jsonb,
  similarity   real
)
language sql stable
as $$
  select
    f.id, f.title, f.content, f.category, f.confidence, f.tags, f.provenance,
    1 - (f.embedding <=> query_embedding) as similarity
  from findings f
  where (match_kb_id is null or f.kb_id = match_kb_id)
    and (match_org_id is null or f.org_id = match_org_id)
    and (match_categories is null or f.category = any(match_categories))
    and f.embedding is not null
    and 1 - (f.embedding <=> query_embedding) >= min_similarity
  order by f.embedding <=> query_embedding
  limit match_count;
$$;
