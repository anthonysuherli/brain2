-- =============================================================================
-- 0002 — KB synopsis (the always-on preamble "spine").
-- One current row per KB; regenerated incrementally as findings grow.
-- Bands are read-time (no findings change); only the spine is stored here.
-- =============================================================================

create table kb_synopsis (
  id                      uuid primary key default uuid_generate_v4(),
  org_id                  uuid not null references orgs(id) on delete cascade,
  kb_id                   uuid not null references kbs(id) on delete cascade,
  content                 jsonb not null default '[]'::jsonb,  -- list[{topic, gloss}]
  finding_count_at_build  integer not null default 0,
  model                   text,
  built_at                timestamptz not null default now(),
  unique (kb_id)
);

create index idx_kb_synopsis_kb on kb_synopsis(kb_id);
create index idx_kb_synopsis_org on kb_synopsis(org_id);

alter table kb_synopsis enable row level security;

-- Same org-membership macro as 0001's business tables (org_id denormalized).
create policy kb_synopsis_select on kb_synopsis for select
  using (org_id in (select org_id from org_members where user_id = auth.uid()));
create policy kb_synopsis_insert on kb_synopsis for insert
  with check (org_id in (select org_id from org_members where user_id = auth.uid()));
create policy kb_synopsis_update on kb_synopsis for update
  using (org_id in (select org_id from org_members where user_id = auth.uid()));
create policy kb_synopsis_delete on kb_synopsis for delete
  using (org_id in (select org_id from org_members where user_id = auth.uid()));
