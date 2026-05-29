-- 0005_kg_schema.sql — the KG "intent" schema (collaborative ontology co-design).
--
--   /knowledge schema → propose → approve → set_kg_intent → kg_schemas(v+1)
--                                                              │
--                          build_graph(use_schema=True) reads highest version
--
-- A KB's KG schema is the user-approved TARGET ONTOLOGY (node types, relation
-- types, a relation-validity map, and competency questions) that softly steers
-- the extraction pass. Stored VERSIONED — every `set` inserts a new row (drift
-- is expected; history is kept). Writes go through the service client, so RLS
-- here only gates org-scoped reads, matching the rest of the schema.

create table kg_schemas (
  id          uuid primary key default uuid_generate_v4(),
  org_id      uuid not null references orgs(id) on delete cascade,
  kb_id       uuid not null references kbs(id) on delete cascade,
  version     int not null default 1,
  schema      jsonb not null,          -- the KGSchema: types, relation_validity, CQs, regime
  created_at  timestamptz not null default now()
);

-- One row per (kb, version); the build reads max(version) per kb.
create unique index kg_schemas_kb_version on kg_schemas(kb_id, version);
create index idx_kg_schemas_kb on kg_schemas(kb_id);

-- RLS — org-scoped select (writes are service-client, RLS-bypassing).
alter table kg_schemas enable row level security;

create policy kg_schemas_select on kg_schemas for select
  using (org_id in (select org_id from org_members where user_id = auth.uid()));
