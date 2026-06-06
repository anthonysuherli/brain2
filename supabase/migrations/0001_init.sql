-- =============================================================================
-- Divergence v0 — initial schema
--
-- Tenancy: personal-org pattern. Every business row carries org_id; one RLS
-- policy per table (org membership). v0 ships with one auto-created org per
-- user; team features ship later as pure UI on top of the same schema.
--
-- Conventions:
--   - UUIDs everywhere (uuid_generate_v4()).
--   - org_id denormalized onto every business table for cheap RLS.
--   - JSONB for open-schema payloads (parts, provenance, properties).
--   - pgvector(1536) for embeddings, HNSW indexed.
--   - Timestamps are timestamptz, default now().
-- =============================================================================

create extension if not exists "uuid-ossp";
create extension if not exists "vector";
create extension if not exists "pg_trgm";  -- gin_trgm_ops on kg_nodes.label

-- -----------------------------------------------------------------------------
-- tenancy
-- -----------------------------------------------------------------------------

create table orgs (
  id              uuid primary key default uuid_generate_v4(),
  name            text not null,
  owner_user_id   uuid not null references auth.users(id) on delete cascade,
  plan            text not null default 'free',
  created_at      timestamptz not null default now()
);

create table org_members (
  org_id          uuid not null references orgs(id) on delete cascade,
  user_id         uuid not null references auth.users(id) on delete cascade,
  role            text not null default 'owner' check (role in ('owner','admin','member','viewer')),
  created_at      timestamptz not null default now(),
  primary key (org_id, user_id)
);

create index idx_org_members_user on org_members(user_id);

-- Auto-create personal org on signup.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  new_org_id uuid;
begin
  insert into orgs (name, owner_user_id)
  values (coalesce(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)) || '''s workspace', new.id)
  returning id into new_org_id;

  insert into org_members (org_id, user_id, role)
  values (new_org_id, new.id, 'owner');

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- -----------------------------------------------------------------------------
-- workspace
-- -----------------------------------------------------------------------------

create table projects (
  id              uuid primary key default uuid_generate_v4(),
  org_id          uuid not null references orgs(id) on delete cascade,
  name            text not null,
  description     text,
  default_kb_id   uuid,
  created_at      timestamptz not null default now()
);

create index idx_projects_org on projects(org_id);

create table kbs (
  id              uuid primary key default uuid_generate_v4(),
  org_id          uuid not null references orgs(id) on delete cascade,
  project_id      uuid not null references projects(id) on delete cascade,
  name            text not null,
  description     text,
  published       boolean not null default false,
  created_at      timestamptz not null default now()
);

create index idx_kbs_project on kbs(project_id);
create index idx_kbs_org on kbs(org_id);

alter table projects
  add constraint projects_default_kb_fk
  foreign key (default_kb_id) references kbs(id) on delete set null
  deferrable initially deferred;

-- -----------------------------------------------------------------------------
-- content
-- -----------------------------------------------------------------------------

create table findings (
  id              uuid primary key default uuid_generate_v4(),
  org_id          uuid not null references orgs(id) on delete cascade,
  kb_id           uuid not null references kbs(id) on delete cascade,
  title           text not null,
  content         text not null,
  category        text,
  confidence      real,
  tags            text[] not null default '{}',
  provenance      jsonb not null default '[]'::jsonb,
  embedding       vector(1536),
  created_at      timestamptz not null default now()
);

create index idx_findings_kb on findings(kb_id);
create index idx_findings_org on findings(org_id);
create index idx_findings_category on findings(category);
create index idx_findings_tags on findings using gin(tags);
create index idx_findings_embedding on findings
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create table kg_nodes (
  id              uuid primary key default uuid_generate_v4(),
  org_id          uuid not null references orgs(id) on delete cascade,
  kb_id           uuid not null references kbs(id) on delete cascade,
  type            text not null,
  label           text not null,
  properties      jsonb not null default '{}'::jsonb,
  embedding       vector(1536),
  created_at      timestamptz not null default now()
);

create index idx_kg_nodes_kb on kg_nodes(kb_id);
create index idx_kg_nodes_type on kg_nodes(type);
create index idx_kg_nodes_label_trgm on kg_nodes using gin (label gin_trgm_ops);
create index idx_kg_nodes_embedding on kg_nodes
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create table kg_edges (
  id                uuid primary key default uuid_generate_v4(),
  org_id            uuid not null references orgs(id) on delete cascade,
  kb_id             uuid not null references kbs(id) on delete cascade,
  source_node_id    uuid not null references kg_nodes(id) on delete cascade,
  target_node_id    uuid not null references kg_nodes(id) on delete cascade,
  relation          text not null,
  properties        jsonb not null default '{}'::jsonb,
  created_at        timestamptz not null default now()
);

create index idx_kg_edges_kb on kg_edges(kb_id);
create index idx_kg_edges_source on kg_edges(source_node_id);
create index idx_kg_edges_target on kg_edges(target_node_id);

-- -----------------------------------------------------------------------------
-- chat
-- -----------------------------------------------------------------------------

create table chat_threads (
  id              uuid primary key default uuid_generate_v4(),
  org_id          uuid not null references orgs(id) on delete cascade,
  user_id         uuid not null references auth.users(id) on delete cascade,
  project_id      uuid references projects(id) on delete set null,
  title           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index idx_chat_threads_user on chat_threads(user_id);

create table chat_messages (
  id              uuid primary key default uuid_generate_v4(),
  org_id          uuid not null references orgs(id) on delete cascade,
  thread_id       uuid not null references chat_threads(id) on delete cascade,
  role            text not null check (role in ('user','assistant','system','tool')),
  parts           jsonb not null default '[]'::jsonb,
  created_at      timestamptz not null default now()
);

create index idx_chat_messages_thread on chat_messages(thread_id, created_at);

-- -----------------------------------------------------------------------------
-- ingestion
-- -----------------------------------------------------------------------------

create table uploads (
  id              uuid primary key default uuid_generate_v4(),
  org_id          uuid not null references orgs(id) on delete cascade,
  kb_id           uuid not null references kbs(id) on delete cascade,
  user_id         uuid not null references auth.users(id) on delete cascade,
  storage_path    text not null,
  mime            text not null,
  size            bigint not null,
  status          text not null default 'pending' check (status in ('pending','processing','completed','failed')),
  error           text,
  finding_ids     uuid[] not null default '{}',
  created_at      timestamptz not null default now()
);

create index idx_uploads_kb on uploads(kb_id);
create index idx_uploads_status on uploads(status);

create table explorations (
  id              uuid primary key default uuid_generate_v4(),
  org_id          uuid not null references orgs(id) on delete cascade,
  kb_id           uuid not null references kbs(id) on delete cascade,
  prompt          text not null,
  status          text not null default 'pending' check (status in ('pending','planning','searching','crawling','extracting','merging','completed','failed')),
  error           text,
  finding_ids     uuid[] not null default '{}',
  started_at      timestamptz,
  completed_at    timestamptz,
  created_at      timestamptz not null default now()
);

create index idx_explorations_kb on explorations(kb_id);

-- -----------------------------------------------------------------------------
-- public api
-- -----------------------------------------------------------------------------

create table api_keys (
  id              uuid primary key default uuid_generate_v4(),
  org_id          uuid not null references orgs(id) on delete cascade,
  kb_id           uuid not null references kbs(id) on delete cascade,
  name            text not null,
  key_prefix      text not null,                -- public part, e.g. "dvg_live_abc12"
  key_hash        text not null,                -- argon2 hash of full key
  last_used_at    timestamptz,
  revoked_at      timestamptz,
  created_at      timestamptz not null default now()
);

create unique index idx_api_keys_prefix on api_keys(key_prefix);
create index idx_api_keys_kb on api_keys(kb_id);

create table api_key_usage (
  id              bigserial primary key,
  api_key_id      uuid not null references api_keys(id) on delete cascade,
  endpoint        text not null,
  ts              timestamptz not null default now(),
  latency_ms      integer,
  status_code     integer
);

create index idx_api_key_usage_key_ts on api_key_usage(api_key_id, ts desc);

-- -----------------------------------------------------------------------------
-- RLS — one pattern everywhere: org membership
-- -----------------------------------------------------------------------------

alter table orgs              enable row level security;
alter table org_members       enable row level security;
alter table projects          enable row level security;
alter table kbs               enable row level security;
alter table findings          enable row level security;
alter table kg_nodes          enable row level security;
alter table kg_edges          enable row level security;
alter table chat_threads      enable row level security;
alter table chat_messages     enable row level security;
alter table uploads           enable row level security;
alter table explorations      enable row level security;
alter table api_keys          enable row level security;
alter table api_key_usage     enable row level security;

-- macro: members can read; owners/admins can write
create policy org_select on orgs for select
  using (id in (select org_id from org_members where user_id = auth.uid()));
create policy org_update on orgs for update
  using (id in (select org_id from org_members where user_id = auth.uid() and role in ('owner','admin')));

-- Non-recursive: a user sees their own membership rows. (Referencing
-- org_members inside its own policy causes infinite recursion — 42P17.)
create policy om_select on org_members for select
  using (user_id = auth.uid());

-- generic CRUD per table — gated on org membership
do $$
declare
  t text;
  tables text[] := array[
    'projects','kbs','findings','kg_nodes','kg_edges',
    'chat_threads','chat_messages','uploads','explorations',
    'api_keys'
  ];
begin
  foreach t in array tables loop
    execute format($f$
      create policy %1$s_select on %1$s for select
        using (org_id in (select org_id from org_members where user_id = auth.uid()));
      create policy %1$s_insert on %1$s for insert
        with check (org_id in (select org_id from org_members where user_id = auth.uid()));
      create policy %1$s_update on %1$s for update
        using (org_id in (select org_id from org_members where user_id = auth.uid()));
      create policy %1$s_delete on %1$s for delete
        using (org_id in (select org_id from org_members where user_id = auth.uid()));
    $f$, t);
  end loop;
end $$;

-- api_key_usage: viewable through the parent api_key's org
create policy aku_select on api_key_usage for select
  using (api_key_id in (
    select id from api_keys
    where org_id in (select org_id from org_members where user_id = auth.uid())
  ));

-- -----------------------------------------------------------------------------
-- Supabase Storage bucket — uploads
-- -----------------------------------------------------------------------------

insert into storage.buckets (id, name, public)
values ('uploads', 'uploads', false)
on conflict (id) do nothing;

-- Storage policy: users read/write objects under <org_id>/<user_id>/...
create policy "upload_owner_select" on storage.objects for select
  using (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] in (
      select org_id::text from org_members where user_id = auth.uid()
    )
  );

create policy "upload_owner_insert" on storage.objects for insert
  with check (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] in (
      select org_id::text from org_members where user_id = auth.uid()
    )
  );

create policy "upload_owner_delete" on storage.objects for delete
  using (
    bucket_id = 'uploads'
    and (storage.foldername(name))[1] in (
      select org_id::text from org_members where user_id = auth.uid()
    )
  );

-- -----------------------------------------------------------------------------
-- RPC: semantic search (used by /v1/preamble + /v1/findings)
-- -----------------------------------------------------------------------------

create or replace function match_findings(
  query_embedding vector(1536),
  match_kb_id     uuid,
  match_count     int default 10,
  min_similarity  real default 0.0
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
  where f.kb_id = match_kb_id
    and f.embedding is not null
    and 1 - (f.embedding <=> query_embedding) >= min_similarity
  order by f.embedding <=> query_embedding
  limit match_count;
$$;
