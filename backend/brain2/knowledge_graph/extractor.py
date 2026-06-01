"""KG extractor — one structured LLM pass over a KB's findings.

    findings (title + category + content) ──► AI Gateway ──► KGExtraction

Mirrors divergence's ``knowledge_graph/extractor.py``: routes through the
AI Gateway (dotted slugs), instructs the schema in the prompt
(``use_json_schema=False``, for the free-form ``properties`` dicts), and never
raises — a failed pass yields an empty graph rather than poisoning the build.

**brain2 adaptation:** the LLM returns label-based edges (``_LLMEdge.source`` /
``_LLMEdge.target`` are label strings); we convert them to integer-indexed
``KGEdge`` objects before returning so the caller (builder) only sees the
canonical brain2 ``KGExtraction`` shape.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from brain2.clients.ai_gateway import structured_completion
from brain2.config import KnowledgeGraphConfig
from brain2.knowledge_graph.models import KGEdge, KGExtraction, KGNode

if TYPE_CHECKING:
    from brain2.knowledge_graph.models import KGSchema

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are building a knowledge graph from a knowledge base's findings.\n"
    "Extract the salient ENTITIES (nodes) and the RELATIONSHIPS (directed edges) "
    "between them.\n\n"
    "RULES:\n"
    "1. Use a single canonical `label` per entity — merge obvious aliases "
    "(e.g. 'OpenAI' and 'OpenAI Inc.' are one node labelled 'OpenAI').\n"
    "2. `type` is a short lowercase ontology class (company, person, technology, "
    "concept, product, place, event, metric, ...). Reuse types across entities.\n"
    "3. Every edge's `source` and `target` MUST exactly match a node `label` you "
    "also return. `relation` is a short verb phrase (acquired, founded_by, "
    "competes_with, part_of, uses).\n"
    "4. Extract only what the findings support — no outside knowledge, no "
    "placeholders. Prefer fewer, well-supported nodes over speculative ones.\n"
    "5. Put supporting attributes in `properties` (free-form key/value).\n"
    "6. GROUND every node and every edge: set `grounded_in` to the finding id(s) that "
    "evidence it. Each finding is prefixed with its id as `(finding_id: <id>)`. Use those "
    "exact ids; give every node and edge at least one."
)


def _schema_block(schema: KGSchema) -> str:
    """Render the approved ontology as a SOFT-guidance addendum to ``_SYSTEM``.

    Lists the preferred node/relation types (with descriptions), the relation-
    validity constraints, and the competency questions the graph must answer.
    Soft mode: out-of-schema signal is KEPT (typed 'other'), never dropped — a
    too-narrow schema degrades gracefully instead of losing findings.

    Adapts from divergence: brain2's ``KGSchema.relation_validity`` is a flat
    ``list[RelationValidity]`` (typed objects) rather than a
    ``dict[str, list[str]]``, so validity is rendered as ``source → target`` pairs.
    """

    def _node_line(nt) -> str:  # noqa: ANN001 — local formatter
        head = f"{nt.name} — {nt.description}" if nt.description else nt.name
        if nt.layer:
            head += f" [layer: {nt.layer}]"
        if nt.attributes:
            attrs = ", ".join(
                f"{a.name}:{a.type}{'*' if a.required else ''}" for a in nt.attributes
            )
            head += f" {{attributes: {attrs}}}"
        return head

    nodes = "; ".join(_node_line(nt) for nt in schema.node_types)
    rels = "; ".join(
        f"{rt.name} — {rt.description}" if rt.description else rt.name
        for rt in schema.relation_types
    )
    # brain2 relation_validity is list[RelationValidity] — render as "src→tgt" pairs.
    validity_pairs = ", ".join(
        f"{rv.source_type}→{rv.target_type}" for rv in schema.relation_validity
    )
    cqs = " ".join(f"- {q}" for q in schema.competency_questions)
    has_attrs = any(nt.attributes for nt in schema.node_types)
    has_layers = any(nt.layer for nt in schema.node_types)
    lines = [
        "\n\nTARGET ONTOLOGY (prefer these classes; do not force-fit):",
        f"  node types: {nodes or '(none)'}",
        f"  relation types: {rels or '(none)'}",
    ]
    if validity_pairs:
        lines.append(f"  legal source→target pairs: {validity_pairs}")
    if cqs:
        lines.append(f"This graph must be able to answer: {cqs}")
    if has_attrs:
        lines.append(
            "For each node, fill `properties` with the declared attributes for its type (key = "
            "attribute name); use the attribute's value type, and include every attribute marked "
            "* (required) when the findings supply it — omit a key rather than inventing a value."
        )
    if has_layers:
        lines.append("Also set `properties.layer` to the node type's declared layer.")
    lines.append(
        "If a salient entity or relation does not fit the ontology, KEEP it: use the "
        'closest class, or `type`/`relation` "other", and add a `properties.note`. '
        "Never drop supported signal to satisfy the schema."
    )
    return "\n".join(lines)


def _catalogue(findings: list[dict], max_finding_chars: int) -> str:
    lines: list[str] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        title = f.get("title", "")
        category = f.get("category", "")
        content = str(f.get("content", ""))[:max_finding_chars]
        fid = f.get("id")
        marker = f" (finding_id: {fid})" if fid else ""
        lines.append(f"### {title} [{category}]{marker}\n{content}")
    return "\n\n".join(lines)


# Entity names too generic to safely text-match against finding bodies.
# Mirrors divergence's guard.
_GENERIC_NAMES = frozenset(
    {
        "entity",
        "relationship",
        "person",
        "system",
        "framework",
        "algorithm",
        "organization",
        "standard",
        "concept",
        "technology",
        "company",
        "product",
        "model",
        "method",
        "tool",
        "service",
        "data",
        "api",
        "other",
    }
)


def _is_specific(name: str) -> bool:
    return len(name.strip()) >= 3 and name.strip().lower() not in _GENERIC_NAMES


# ---------------------------------------------------------------------------
# LLM-facing extraction models (label-based edges — converted before return)
# ---------------------------------------------------------------------------


class _LLMNode(BaseModel):
    """One entity as returned by the LLM."""

    label: str = Field(description="Canonical name of the entity")
    type: str = Field(default="concept", description="Short lowercase ontology class")
    properties: dict[str, Any] = Field(default_factory=dict)
    grounded_in: list[str] = Field(
        default_factory=list, description="Finding ids that evidence this entity"
    )


class _LLMEdge(BaseModel):
    """One directed relation — source/target are label strings (LLM-friendly)."""

    source: str = Field(description="Label of the source node")
    target: str = Field(description="Label of the target node")
    relation: str = Field(description="Short verb phrase (e.g. 'uses', 'part_of')")
    properties: dict[str, Any] = Field(default_factory=dict)
    grounded_in: list[str] = Field(default_factory=list)


class _LLMExtraction(BaseModel):
    """Raw extraction produced by the LLM — label-indexed edges."""

    nodes: list[_LLMNode] = Field(default_factory=list)
    edges: list[_LLMEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Grounding repair
# ---------------------------------------------------------------------------


def backfill_grounding(extraction: _LLMExtraction, findings: list[dict]) -> int:
    """Deterministic repair: fill empty ``grounded_in`` by case-insensitive
    substring match of an entity's label against finding text.

    Ported from divergence. The generic-name guard prevents a vague label
    from matching everything. Returns the count of nodes+edges still ungrounded
    after the pass."""
    texts = [
        (str(f.get("id")), f"{f.get('title', '')} {f.get('content', '')}".lower())
        for f in findings
        if isinstance(f, dict) and f.get("id")
    ]
    label_by_norm = {n.label.strip().lower(): n.label for n in extraction.nodes}

    def _match(name: str) -> list[str]:
        if not _is_specific(name):
            return []
        needle = name.strip().lower()
        return [fid for fid, text in texts if needle in text]

    unresolved = 0
    for node in extraction.nodes:
        if node.grounded_in:
            continue
        node.grounded_in = _match(node.label)
        if not node.grounded_in:
            unresolved += 1

    for edge in extraction.edges:
        if edge.grounded_in:
            continue
        matched: set[str] = set()
        for endpoint in (edge.source, edge.target):
            label = label_by_norm.get(endpoint.strip().lower(), endpoint)
            matched.update(_match(label))
        edge.grounded_in = sorted(matched)
        if not edge.grounded_in:
            unresolved += 1

    return unresolved


# ---------------------------------------------------------------------------
# Label→index conversion
# ---------------------------------------------------------------------------


def _norm(label: str) -> str:
    """Normalize a label: trim, lower, collapse whitespace."""
    return " ".join(label.strip().lower().split())


def _to_kg_extraction(llm: _LLMExtraction) -> KGExtraction:
    """Convert LLM-facing label-based extraction to brain2's index-based ``KGExtraction``.

    Nodes are converted 1:1; edges whose source/target label doesn't resolve to a
    known node are dropped (dangling), and self-loops are skipped."""
    nodes = [
        KGNode(
            label=n.label,
            type=n.type,
            properties=n.properties,
            grounded_in=n.grounded_in,
        )
        for n in llm.nodes
    ]
    label_to_idx: dict[str, int] = {_norm(n.label): i for i, n in enumerate(nodes)}

    edges: list[KGEdge] = []
    seen: set[tuple[int, int, str]] = set()
    for e in llm.edges:
        si = label_to_idx.get(_norm(e.source))
        ti = label_to_idx.get(_norm(e.target))
        if si is None or ti is None or si == ti:
            continue
        key = (si, ti, e.relation)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            KGEdge(
                source=si,
                target=ti,
                relation=e.relation,
                properties=e.properties,
                grounded_in=e.grounded_in,
            )
        )

    return KGExtraction(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_graph(
    findings: list[dict], cfg: KnowledgeGraphConfig, schema: KGSchema | None = None
) -> KGExtraction:
    """Extract a knowledge graph from the KB's findings. Returns an empty graph on failure.

    When ``schema`` is given, its approved ontology is appended to the system
    prompt as SOFT guidance (prefer those types; keep out-of-schema signal as
    'other'). When ``schema is None``, the prompt is byte-identical to the
    free-form default.

    Returns a ``KGExtraction`` with integer-indexed edges (brain2 canonical shape).
    """
    if not findings:
        return KGExtraction()
    system = _SYSTEM + (_schema_block(schema) if schema else "")
    user = _catalogue(findings, cfg.max_finding_chars)
    try:
        llm_extraction: _LLMExtraction = await structured_completion(
            model=cfg.extraction_model,
            response_format=_LLMExtraction,
            system=system,
            user=user,
            temperature=cfg.temperature,
            fallback_model=cfg.extraction_fallback_model,
            reasoning_effort=cfg.reasoning_effort,
            # Free-form `properties` dicts — strict json_schema would empty them.
            use_json_schema=False,
        )
    except Exception as exc:  # noqa: BLE001 — extraction is best-effort
        logger.warning("KG extraction failed: %s", exc)
        return KGExtraction()
    # Deterministic provenance repair: fill any grounded_in the model left empty.
    unresolved = backfill_grounding(llm_extraction, findings)
    if unresolved:
        logger.info(
            "KG extraction: %d node(s)/edge(s) left ungrounded after backfill", unresolved
        )
    return _to_kg_extraction(llm_extraction)
