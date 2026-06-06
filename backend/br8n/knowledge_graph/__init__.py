"""br8n knowledge-graph layer.

Scope is narrow on purpose: br8n ships a single, automatic **activity** graph
(per user, cross-repo, populated on every capture), not delapan's generic
user-curated KG. This package carries:

- ``models`` — node/edge data models shared across the layer
- ``activity`` — builder, extractor, and query surfaces for the activity graph
- ``schema`` — KG intent schema layer: ``propose_schema``, ``validate_schema``,
  and the ``KGSchema`` model (node types, relation types, relation validity,
  competency questions, and soft/hard regime)

The graph is persisted through the ``Store`` protocol, so it works on both the
local SQLite and cloud Supabase tiers.
"""
