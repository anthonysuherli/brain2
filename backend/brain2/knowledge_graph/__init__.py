"""brain2 knowledge-graph layer.

Scope is narrow on purpose: brain2 ships a single, automatic **activity** graph
(per user, cross-repo, populated on every capture), not divergence's generic
user-curated KG. So this package carries only the node/edge data models
(``models``) and the activity builder/extractor/surfaces (``activity``). The
graph is persisted through the ``Store`` protocol, so it works on both the local
SQLite and cloud Supabase tiers.
"""
