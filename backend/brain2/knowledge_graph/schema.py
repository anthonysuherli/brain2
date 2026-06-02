"""KG intent schema — the user-approved TARGET ONTOLOGY for a KB's graph.

    findings ─► propose_schema (LLM, grounded) ─► KGSchema ─► user approves ─► persist
                                                     │
                             extract_graph(schema=…) reads it as SOFT guidance

Pure module — no Supabase, no FastAPI (mirrors the ``exploration/`` boundary). The
proposer mines the KB's findings for candidate entity/relation classes and the
competency questions the graph should answer; the user edits/approves the result;
``build_graph(use_schema=True)`` then feeds it to the extractor. ``regime`` is "soft"
in v1: the schema steers extraction but never forces out-of-schema signal to be
dropped (the extractor keeps it as type "other"). Authoring never raises — a model
hiccup falls back to a deterministic proposal.

Ported from delapan's ``knowledge_graph/schema.py`` with two adaptations:
1. ``relation_validity`` is a flat ``list[RelationValidity]`` (typed objects)
   rather than a ``dict[str, list[str]]`` — cleaner JSONB storage.
2. LLM calls route through brain2's AI Gateway client (dotted model slugs:
   ``anthropic/claude-sonnet-4.6``), matching the exploration pipeline.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from brain2.clients.ai_gateway import structured_completion
from brain2.config import KnowledgeGraphConfig
from brain2.knowledge_graph.models import (
    _ATTR_TYPES,
    Attribute,
    KGSchema,
    NodeType,
    RelationType,
    RelationValidity,
)

logger = logging.getLogger(__name__)

# Fallback ontology when the KB is empty and there's no emergent graph to mine —
# gives the user something to edit even on a sparse KB.
_DEFAULT_NODE_TYPES = ["repo", "branch", "file", "session", "task"]
_DEFAULT_RELATIONS = ["contains", "modified", "branched_from", "depends_on", "related_to"]


# ---------------------------------------------------------------------------
# LLM-facing proposal shape (flat relation_validity for the prompt)
# ---------------------------------------------------------------------------


class _RelationValidityProposal(BaseModel):
    """LLM-facing shape for one validity pair."""

    source_type: str
    target_type: str


class _SchemaProposal(BaseModel):
    """LLM-facing shape — same fields as KGSchema minus persistence-only ``regime``/``version``."""

    node_types: list[NodeType] = Field(default_factory=list)
    relation_types: list[RelationType] = Field(default_factory=list)
    relation_validity: list[_RelationValidityProposal] = Field(default_factory=list)
    competency_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are designing the SCHEMA (intent) of a knowledge graph that will be built "
    "from a knowledge base's findings. Propose a TARGET ONTOLOGY a person can review "
    "and approve.\n\n"
    "Return:\n"
    "- node_types: 4-10 entity classes. Each has a short lowercase `name`, a one-line "
    "`description`, and 2-3 `examples` — REAL entity names taken from the findings. Also give "
    "each class:\n"
    "    • `attributes`: 2-4 typed properties instances of the class should carry, each with a "
    "snake_case `name`, a `type` (one of: text, number, date, url, list, bool), `required`, and a "
    "one-line `description`. Draw them from properties the findings actually report.\n"
    "    • `layer`: an optional short grouping/plane the class sits in (cluster related classes — "
    "e.g. for a codebase 'orchestration'/'interface'/'data'; for a research KB a domain grouping). "
    "Leave '' if no natural grouping.\n"
    "- relation_types: 4-12 directed relation classes. Each has a short snake_case "
    "verb-phrase `name` (e.g. contains, depends_on, branched_from) and a `description`.\n"
    "- relation_validity: a flat list of objects, each with `source_type` and `target_type` "
    "(both must be node_type names you declared), representing legal source→target pairs across "
    'ALL relations. For example: [{"source_type": "repo", "target_type": "branch"}].\n'
    "- competency_questions: 3-6 questions the finished graph should be able to answer "
    "— what someone working with this KB most likely wants to know.\n\n"
    "Ground every class AND attribute in what the findings ACTUALLY contain — no speculative types "
    "or properties. Prefer a small, coherent ontology over an exhaustive one."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _catalogue(findings: list[dict], max_finding_chars: int) -> str:
    """Render findings as a markdown catalogue for the LLM prompt."""
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


def _emergent_hint(emergent: dict | None) -> str:
    """A short prompt addendum biasing reuse of an already-built graph's ontology."""
    if not emergent:
        return ""
    types = ", ".join(emergent.get("node_types") or []) or "(none)"
    rels = ", ".join(emergent.get("relations") or []) or "(none)"
    return (
        "\n\nAn earlier graph build used these classes — reuse them where they fit, "
        f"rather than inventing near-duplicates:\nnode types: {types}\nrelations: {rels}"
    )


def _fallback_schema(emergent: dict | None) -> KGSchema:
    """Deterministic proposal — reuse the emergent ontology if a graph exists, else
    brain2's default activity-graph classes. Never raises; gives the user something to edit."""
    node_names = (emergent or {}).get("node_types") or _DEFAULT_NODE_TYPES
    rel_names = (emergent or {}).get("relations") or _DEFAULT_RELATIONS
    return KGSchema(
        node_types=[NodeType(name=n) for n in node_names],
        relation_types=[RelationType(name=r) for r in rel_names],
        relation_validity=[],
        competency_questions=[
            "What are the key entities and how are they connected?",
            "Which entities are most central to this knowledge base?",
        ],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def propose_schema(
    findings: list[dict], cfg: KnowledgeGraphConfig, *, emergent: dict | None = None
) -> KGSchema:
    """Draft a target ontology from the KB's findings.

    Falls back to a deterministic proposal on empty input or model failure — never raises.
    Routes through the AI Gateway (``anthropic/claude-sonnet-4.6`` dotted slugs), matching
    the exploration pipeline convention.
    """
    if not findings:
        return _fallback_schema(emergent)
    user = _catalogue(findings, cfg.max_finding_chars) + _emergent_hint(emergent)
    try:
        proposal = await structured_completion(
            model=cfg.extraction_model,
            response_format=_SchemaProposal,
            system=_SYSTEM,
            user=user,
            temperature=cfg.temperature,
            fallback_model=cfg.extraction_fallback_model,
            reasoning_effort=cfg.reasoning_effort,
            use_json_schema=False,  # free-form relation_validity list
        )
    except Exception as exc:  # noqa: BLE001 — proposal is best-effort
        logger.warning("KG schema proposal failed: %s", exc)
        return _fallback_schema(emergent)
    if not proposal.node_types:
        return _fallback_schema(emergent)
    return KGSchema(
        node_types=proposal.node_types,
        relation_types=proposal.relation_types,
        relation_validity=[
            RelationValidity(source_type=rv.source_type, target_type=rv.target_type)
            for rv in proposal.relation_validity
        ],
        competency_questions=proposal.competency_questions,
    )


def validate_schema(schema: KGSchema) -> list[str]:
    """Structural checks. Returns a list of human-readable errors ([] = valid).

    Catches the mistakes a hand-edited schema makes: no node types, attribute
    types outside the allowed set, duplicate attribute names, or relation_validity
    entries that reference node type names not declared in ``node_types``.
    """
    errors: list[str] = []
    node_names = {nt.name for nt in schema.node_types}

    if not node_names:
        errors.append("schema has no node_types")

    # Typed attributes: each must declare a known value type, and names must be
    # unique within a class (a dupe would silently overwrite at extraction time).
    for nt in schema.node_types:
        seen: set[str] = set()
        for attr in nt.attributes:
            if attr.type not in _ATTR_TYPES:
                errors.append(
                    f"node type '{nt.name}' attribute '{attr.name}' has unknown type "
                    f"'{attr.type}' (expected one of {', '.join(_ATTR_TYPES)})"
                )
            if attr.name in seen:
                errors.append(f"node type '{nt.name}' declares attribute '{attr.name}' twice")
            seen.add(attr.name)

    # relation_validity: each source_type / target_type must name a declared node type.
    for rv in schema.relation_validity:
        for side, label in (("source_type", rv.source_type), ("target_type", rv.target_type)):
            if label not in node_names:
                errors.append(f"relation_validity {side} '{label}' references undeclared node type")
    return errors


# Re-export the public schema types so callers can do:
#   from brain2.knowledge_graph.schema import KGSchema, validate_schema
__all__ = [
    "Attribute",
    "KGSchema",
    "NodeType",
    "RelationType",
    "RelationValidity",
    "propose_schema",
    "validate_schema",
]
