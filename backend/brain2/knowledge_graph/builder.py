"""KG builder — gather findings, extract a graph, collapse nodes, persist.

    findings ─► extract_graph ─► collapse nodes ─► upsert_kg_nodes ─► kg_nodes
                                               └─► resolve edges → ids ─► kg_edges

Ported from divergence's ``knowledge_graph/builder.py`` with three key adaptations:

1. **Store routing** — all persistence goes through ``get_store(ctx.access_token,
   org_id=ctx.org_id)`` instead of the service client directly. The entry paths
   (MCP tool, future REST endpoint) verify KB ownership before calling.

2. **Index-based edges** — brain2's ``KGExtraction.edges`` use integer indices
   into ``nodes[]`` (set by the extractor). ``_resolve_edges`` maps those indices
   to persisted node IDs via the ``label_to_id`` map built during upsert.

3. **clear_kg** — ``rebuild=True`` calls ``store.clear_kg(kb_id)`` *after*
   extraction succeeds (not before); if extraction fails the old graph is
   preserved. The store owns the table-access pattern.

**YAGNI cuts (v1):**
- ``refresh_project_description`` — not implemented; add as a follow-up when the
  project-description field is used.
- ``schedule_kg_update`` / auto-trigger after explore — not implemented; add when
  the explore pipeline is wired in brain2.
- Incremental build (``finding_ids`` parameter) — raises ``NotImplementedError``
  for now; ``match_kg_nodes``-based vector dedupe exists on the Store when needed.
"""

from __future__ import annotations

import logging

from brain2.agent.state import TenantContext
from brain2.clients.embeddings import embed_batch
from brain2.config import get_config
from brain2.knowledge_graph.extractor import norm, extract_graph
from brain2.knowledge_graph.models import KGEdge, KGExtraction, KGNode, KGSchema
from brain2.store import get_store

logger = logging.getLogger(__name__)


def _collapse_nodes(nodes: list[KGNode]) -> list[KGNode]:
    """Merge extracted nodes sharing a normalized label (first-seen order).

    The first node's ``type`` wins; properties are shallow-merged with the first
    winning on key conflicts. Dropped nodes' surface labels (plus any aliases they
    already carried) are accumulated onto the survivor's ``properties.aliases``,
    ordered and de-duped (the survivor's own canonical label is never added as its
    own alias).

    Note: brain2's ``KGNode`` has no ``aliases`` field — aliases are stored in
    ``properties["aliases"]`` as a list.
    """
    merged: dict[str, KGNode] = {}
    for n in nodes:
        key = norm(n.label)
        if not key:
            continue
        if key in merged:
            existing = merged[key]
            # Properties: existing wins on conflict.
            props = {**n.properties, **existing.properties}
            # Grounding: union, ordered.
            grounded = list(dict.fromkeys([*existing.grounded_in, *n.grounded_in]))
            # Aliases: accumulated from the dropped node's surface label.
            existing_aliases = list(existing.properties.get("aliases") or [])
            aliases = list(
                dict.fromkeys(
                    a
                    for a in [*existing_aliases, n.label, *list(n.properties.get("aliases") or [])]
                    if a and a != existing.label
                )
            )
            props["aliases"] = aliases
            merged[key] = existing.model_copy(
                update={"properties": props, "grounded_in": grounded}
            )
        else:
            merged[key] = n
    return list(merged.values())


def _resolve_edges(extraction: KGExtraction, label_to_id: dict[str, str]) -> list[dict]:
    """Map each edge's integer source/target indices to node ids via ``label_to_id``.

    The index maps to the pre-collapse node label, which is then normed and looked
    up in ``label_to_id``. Drops dangling endpoints + self-loops; de-duplicates on
    (source_id, target_id, relation). ``extraction.nodes`` are the **pre-persist**
    collapsed nodes (same order as the upsert)."""
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    node_labels = [n.label for n in extraction.nodes]

    for e in extraction.edges:
        if e.source >= len(node_labels) or e.target >= len(node_labels):
            continue
        src_key = norm(node_labels[e.source])
        tgt_key = norm(node_labels[e.target])
        sid = label_to_id.get(src_key)
        tid = label_to_id.get(tgt_key)
        if not sid or not tid or sid == tid:
            continue
        key = (sid, tid, e.relation)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "source_node_id": sid,
                "target_node_id": tid,
                "relation": e.relation,
                "properties": e.properties,
                "grounded_in": e.grounded_in,
            }
        )
    return out


def _load_intent(store, kb_id: str) -> KGSchema | None:
    """Read the KB's highest-version intent schema, if any.

    ``get_kg_intent`` returns ``{"version": N, "schema": <dict>}`` — brain2's
    format. We read ``row["schema"]`` (NOT the top-level dict) and validate it
    as a ``KGSchema``. Defensive: a malformed stored schema logs and yields
    ``None`` (free-form fallback), never raises.
    """
    raw = store.get_kg_intent(kb_id)
    if not raw:
        return None
    schema_dict = raw.get("schema") or {}
    if not schema_dict:
        return None
    try:
        return KGSchema.model_validate(schema_dict)
    except Exception:  # noqa: BLE001 — a bad stored schema must not sink the build
        logger.warning("KB %s has a malformed KG intent schema; building free-form", kb_id)
        return None


async def build_graph(
    ctx: TenantContext,
    *,
    max_findings: int | None = None,
    rebuild: bool = True,
    use_schema: bool = True,
    finding_ids: list[str] | None = None,
) -> dict:
    """Extract entities/relations from the KB's findings and persist them.

    ``rebuild=True`` (default) clears the KB's existing nodes/edges *after*
    extraction succeeds, via ``store.clear_kg(kb_id)`` — if extraction fails the
    old graph is preserved. Node dedupe via ``upsert_kg_nodes`` collapses
    near-duplicate entities within the pass.

    ``use_schema=True`` (default) loads the KB's approved intent schema (if one
    was set via ``set_kg_intent``) and steers extraction with it as SOFT guidance;
    with no schema set, or ``use_schema=False``, extraction is free-form.

    **Incremental build** (``finding_ids`` parameter) — not implemented in v1.
    Raises ``NotImplementedError``; add when the explore pipeline is wired in
    brain2 and ``match_kg_nodes``-based vector dedupe is needed.

    Returns ``{"findings_scanned", "nodes_created", "edges_created",
    "node_count", "edge_count"}``.
    """
    if finding_ids:
        raise NotImplementedError(
            "Incremental KG build (finding_ids) is not implemented in brain2 v1. "
            "Run a full rebuild instead."
        )

    cfg = get_config().knowledge_graph
    store = get_store(ctx.access_token, org_id=ctx.org_id)

    n = max_findings or cfg.max_findings
    result = store.list_findings(ctx.kb_id, limit=n)
    findings = [f for f in (result.get("findings") or []) if isinstance(f, dict)]

    if not findings:
        return {
            "findings_scanned": 0,
            "nodes_created": 0,
            "edges_created": 0,
            "node_count": 0,
            "edge_count": 0,
        }

    schema = _load_intent(store, ctx.kb_id) if use_schema else None
    extraction: KGExtraction = await extract_graph(findings, cfg, schema)
    collapsed = _collapse_nodes(extraction.nodes)[: cfg.max_nodes]

    if rebuild:
        store.clear_kg(ctx.kb_id)

    # Build a parallel KGExtraction with collapsed nodes so _resolve_edges can
    # walk extraction.nodes by the same indices (after collapse, indices shift —
    # re-index edges against collapsed nodes).
    collapsed_norm_set = {norm(n.label) for n in collapsed}
    # Remap original node indices → collapsed node indices (or None if dropped).
    orig_to_collapsed: dict[int, int] = {}
    for orig_idx, orig_node in enumerate(extraction.nodes):
        k = norm(orig_node.label)
        if k in collapsed_norm_set:
            # Find position in collapsed list
            for ci, cn in enumerate(collapsed):
                if norm(cn.label) == k:
                    orig_to_collapsed[orig_idx] = ci
                    break

    # Remap edges to collapsed indices.
    remapped_edges: list[KGEdge] = []
    for e in extraction.edges:
        si = orig_to_collapsed.get(e.source)
        ti = orig_to_collapsed.get(e.target)
        if si is None or ti is None or si == ti:
            continue
        remapped_edges.append(
            KGEdge(
                source=si, target=ti, relation=e.relation,
                properties=e.properties, grounded_in=e.grounded_in,
            )
        )

    collapsed_extraction = KGExtraction(nodes=collapsed, edges=remapped_edges)

    # --- persist nodes -------------------------------------------------------
    label_to_id: dict[str, str] = {}
    nodes_created = 0

    if collapsed:
        # Embed node labels for semantic subgraph seeding.
        embeddings: list[list[float]] = []
        try:
            embeddings = await embed_batch([nd.label for nd in collapsed])
        except Exception as exc:  # noqa: BLE001 — embeddings only power query; degrade gracefully
            logger.warning("KG node embedding failed (%s); persisting without vectors", exc)

        node_rows = [
            {
                "org_id": ctx.org_id,
                "type": nd.type,
                "label": nd.label,
                "properties": nd.properties,
                "grounded_in": nd.grounded_in,
                "embedding": embeddings[i] if i < len(embeddings) else None,
            }
            for i, nd in enumerate(collapsed)
        ]
        node_ids = await store.upsert_kg_nodes(ctx.kb_id, node_rows)
        nodes_created = len(node_ids)

        for nd, nid in zip(collapsed, node_ids):
            label_to_id[norm(nd.label)] = nid

    # --- persist edges -------------------------------------------------------
    edges_created = 0
    if collapsed_extraction.edges and label_to_id:
        edge_dicts = _resolve_edges(collapsed_extraction, label_to_id)
        if edge_dicts:
            edge_rows = [{"org_id": ctx.org_id, **e} for e in edge_dicts]
            edges_created = await store.upsert_kg_edges(ctx.kb_id, edge_rows)

    # --- final totals --------------------------------------------------------
    stats = store.kg_stats(ctx.kb_id)
    return {
        "findings_scanned": len(findings),
        "nodes_created": nodes_created,
        "edges_created": edges_created,
        "node_count": stats.get("node_count", 0),
        "edge_count": stats.get("edge_count", 0),
    }
