-- 0007_kb_init_offered.sql — offer-once stamp for the first-run KG schema wizard offer.
-- Prevents re-offering the schema setup on every session after the first.
-- Written by brain2_mark_init_offered MCP tool after the offer is surfaced.
alter table kbs add column if not exists init_offered_at timestamptz;
