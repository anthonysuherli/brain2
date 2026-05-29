-- =============================================================================
-- 0004 — KB/KG monitoring: append-only access events + daily rollups.
--
-- Two axes of monitoring; this migration backs the USAGE axis (the health axis
-- reads existing findings/kg_nodes/kg_edges, no new tables):
--
--   access_events       append-only source of truth — one row per consumption
--                        event (node/edge/finding/preamble access) across the
--                        three surfaces (mcp | v1_api | agent).
--   access_rollup_daily  materialized per-day aggregate — cheap hotspot/billing
--                        reads as raw events grow. Recomputed (not incremented)
--                        by rollup_access_events(day), so it is idempotent.
--
-- Deliberately decoupled from kg_nodes/kg_edges: a full KG rebuild
-- (divergence_build_graph rebuild=true) clears those tables, and we must NOT
-- lose access history when it does. target_id is a loose uuid reference, not a
-- FK — events outlive the nodes/edges/findings they point at.
--
-- Writes go through the SERVICE client (fire-and-forget, like api_key_usage in
-- 0001); RLS select policies exist only so user-scoped clients can read.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- access_events — append-only
-- -----------------------------------------------------------------------------

create table access_events (
  id            bigserial primary key,
  org_id        uuid not null references orgs(id) on delete cascade,
  kb_id         uuid not null references kbs(id) on delete cascade,
  target_type   text not null check (target_type in ('node','edge','finding','preamble')),
  target_id     uuid,                  -- null for preamble (kb-level access)
  surface       text not null check (surface in ('mcp','v1_api','agent')),
  api_key_id    uuid references api_keys(id) on delete set null,  -- null for jwt/mcp
  query_text    text,                  -- the q/focus that surfaced it (nullable)
  ts            timestamptz not null default now()
);

create index idx_access_events_kb_ts on access_events(kb_id, ts desc);
create index idx_access_events_target on access_events(kb_id, target_type, target_id);
create index idx_access_events_key_ts on access_events(api_key_id, ts desc);

-- -----------------------------------------------------------------------------
-- access_rollup_daily — materialized aggregate
-- -----------------------------------------------------------------------------

create table access_rollup_daily (
  id            bigserial primary key,
  kb_id         uuid not null references kbs(id) on delete cascade,
  org_id        uuid not null references orgs(id) on delete cascade,
  day           date not null,
  target_type   text not null,
  target_id     uuid,                  -- nullable → can't live in a PK
  surface       text not null,
  api_key_id    uuid,                  -- nullable → can't live in a PK
  hit_count     integer not null default 0
);

-- Upsert key. PK columns can't be null, and target_id/api_key_id both can be,
-- so we use a surrogate PK + a UNIQUE NULLS NOT DISTINCT index (PG15+) as the
-- ON CONFLICT target — NULLS NOT DISTINCT makes two null target_ids collide
-- (the default treats nulls as distinct, which would duplicate rollup rows).
create unique index uq_access_rollup_daily
  on access_rollup_daily (kb_id, day, target_type, target_id, surface, api_key_id)
  nulls not distinct;

create index idx_access_rollup_kb_day on access_rollup_daily(kb_id, day desc);
create index idx_access_rollup_key_day on access_rollup_daily(api_key_id, day desc);

-- -----------------------------------------------------------------------------
-- rollup_access_events — recompute one day's rollup from raw events (idempotent)
-- -----------------------------------------------------------------------------
-- Recomputes the full day (hit_count = the recomputed count, NOT += ), so
-- running it twice for the same day is a no-op on the totals. Run nightly for
-- "yesterday", then prune access_events older than the retention window — in
-- that order, or un-rolled events are lost.

create or replace function rollup_access_events(p_day date)
returns integer
language plpgsql
as $$
declare
  affected integer;
begin
  insert into access_rollup_daily
    (kb_id, org_id, day, target_type, target_id, surface, api_key_id, hit_count)
  select
    e.kb_id, e.org_id, p_day, e.target_type, e.target_id, e.surface, e.api_key_id,
    count(*)::integer
  from access_events e
  where e.ts >= p_day::timestamptz
    and e.ts <  (p_day + 1)::timestamptz
  group by e.kb_id, e.org_id, e.target_type, e.target_id, e.surface, e.api_key_id
  on conflict (kb_id, day, target_type, target_id, surface, api_key_id)
    do update set hit_count = excluded.hit_count;

  get diagnostics affected = row_count;
  return affected;
end;
$$;

-- -----------------------------------------------------------------------------
-- RLS — org-scoped select (writes are service-client, RLS-bypassing)
-- -----------------------------------------------------------------------------

alter table access_events      enable row level security;
alter table access_rollup_daily enable row level security;

create policy access_events_select on access_events for select
  using (org_id in (select org_id from org_members where user_id = auth.uid()));

create policy access_rollup_daily_select on access_rollup_daily for select
  using (org_id in (select org_id from org_members where user_id = auth.uid()));
