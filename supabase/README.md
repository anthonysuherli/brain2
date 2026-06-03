# supabase/ — schema & migrations

## Ownership & license

These migrations define the Postgres + pgvector schema for brain2's **cloud
tier** (`SupabaseStore`). They originated alongside the Delapan engine and were
copied into brain2 as part of the self-contained fork.

**brain2's copy of this schema is licensed under brain2's [MIT License](../LICENSE).**
The author (Anthony Suherli) owns both brain2 and Delapan and re-licenses this
copy under MIT here. Delapan keeps its own copy under its own
(source-available / BUSL) license. The two are **separate copies**, not a shared
file with two licenses — which resolves the "a migration can't be MIT here and
BUSL there" ambiguity noted in [../.github/LICENSING.md](../.github/LICENSING.md).

## Syncing

Treat these like the rest of the engine fork (see `../CLAUDE.md`): when the
schema improves in Delapan, apply the change here **manually** (copy the
migration, rename any `delapan`/`divergence` references). Do **not** introduce a
cross-repo dependency or symlink — brain2 stays standalone, and brain2 owns
`supabase/migrations/` for its own deployments.

## Note on the local tier

The free/local tier does **not** use these migrations. `SQLiteStore` builds its
own schema at runtime via `_ensure_schema()` (`CREATE TABLE IF NOT EXISTS` in
`backend/brain2/store/`). These SQL files are only for the Supabase-backed cloud
tier.

## Migrations

| File | Purpose |
|---|---|
| `0001_init.sql` | Initial schema — orgs, KBs, findings; personal-org tenancy + RLS. |
| `0002_kb_synopsis.sql` | KB synopsis storage. |
| `0003_match_kg_nodes.sql` | `match_kg_nodes` RPC (semantic KG node match). |
| `0004_kb_kg_monitoring.sql` | KB/KG monitoring columns. |
| `0005_kg_schema.sql` | Knowledge-graph nodes/edges schema. |
| `0006_kg_grounded_in.sql` | `grounded_in` KG edge relation. |
| `0007_kb_init_offered.sql` | First-run-init "offered" stamp. |
