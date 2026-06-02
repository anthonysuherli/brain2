"""Graph data models — the carriers between extraction and the Store.

Ported from delapan's KG models (the only piece of that layer brain2 reuses).
``properties`` are free-form dicts; an ``embedding`` rides along on a node so the
Store can persist it for semantic subgraph seeding. Dedupe is by exact
``(type, label)`` at the Store, so these models stay pure data.

Also contains the KG intent schema models (``KGSchema`` and sub-types) — the
user-approved target ontology. These are kept here rather than in ``schema.py``
so downstream code (extractor, MCP layer) can import the shapes without pulling
in the LLM proposer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# KG intent schema (ported + adapted from delapan — list-of-objects variant)
# ---------------------------------------------------------------------------

# Valid attribute value types — same set as delapan.
_ATTR_TYPES: tuple[str, ...] = ("text", "number", "date", "url", "list", "bool")


class Attribute(BaseModel):
    """A typed property a node class carries (e.g. service.language : text)."""

    name: str = Field(description="Short snake_case property name, e.g. 'founded_year'")
    type: str = Field(default="text", description=f"Value type — one of {', '.join(_ATTR_TYPES)}")
    required: bool = Field(default=False, description="Whether every instance should carry it")
    description: str = Field(default="", description="One-line meaning of the property")


class NodeType(BaseModel):
    """One entity class in the target ontology."""

    name: str = Field(description="Short lowercase class name, e.g. 'service'")
    description: str = Field(default="", description="One-line meaning of this class")
    examples: list[str] = Field(
        default_factory=list, description="2-3 real entity names drawn from the findings"
    )
    attributes: list[Attribute] = Field(
        default_factory=list,
        description="2-4 typed properties instances of this class should carry",
    )
    layer: str = Field(
        default="",
        description=(
            "Optional grouping/plane this class sits in (e.g. 'orchestration', 'interface', "
            "'data', 'infrastructure'). Free-form; used to cluster the graph by tier."
        ),
    )


class RelationType(BaseModel):
    """One directed relation class in the target ontology."""

    name: str = Field(description="Short snake_case verb phrase, e.g. 'calls'")
    description: str = Field(default="", description="One-line meaning of this relation")


class RelationValidity(BaseModel):
    """A legal source→target pair for a relation (tied to a specific relation name via the
    containing KGSchema). Stored as a flat list rather than a dict so it round-trips cleanly
    through JSON / Supabase JSONB without key-space constraints."""

    source_type: str = Field(description="Node type name that may be the source")
    target_type: str = Field(description="Node type name that may be the target")


class KGSchema(BaseModel):
    """A KB's approved KG intent — the artifact persisted to ``kg_schemas``."""

    node_types: list[NodeType] = Field(default_factory=list)
    relation_types: list[RelationType] = Field(default_factory=list)
    # Flat list of legal source→target pairs across ALL relations.
    # (Delapan uses dict[relation_name, list[str]]; brain2 uses a flat list
    # of typed objects so the shape is uniform and JSONB-friendly.)
    relation_validity: list[RelationValidity] = Field(default_factory=list)
    competency_questions: list[str] = Field(default_factory=list)
    regime: Literal["soft"] = "soft"
    version: int = 1


class KGNode(BaseModel):
    """One entity. ``label`` is its canonical name; ``type`` its ontology class."""

    label: str = Field(
        description="Canonical name of the entity (e.g. 'brain2' or 'store/base.py')"
    )
    type: str = Field(description="Entity class — repo | branch | file | session | task")
    properties: dict[str, Any] = Field(default_factory=dict)
    grounded_in: list[str] = Field(
        default_factory=list, description="Finding ids that evidence this entity"
    )
    embedding: list[float] | None = Field(
        default=None, description="Label embedding, for semantic subgraph seeding"
    )


class KGEdge(BaseModel):
    """A directed relation between two nodes, referenced by their index in the
    extraction's ``nodes`` list (collision-proof — labels can repeat across types)."""

    source: int = Field(description="Index into nodes[] of the source")
    target: int = Field(description="Index into nodes[] of the target")
    relation: str = Field(description="Relation type, a short verb phrase (e.g. 'edited')")
    properties: dict[str, Any] = Field(default_factory=dict)
    grounded_in: list[str] = Field(default_factory=list)


class KGExtraction(BaseModel):
    """Nodes + edges produced by one extraction pass over a snapshot."""

    nodes: list[KGNode] = Field(default_factory=list)
    edges: list[KGEdge] = Field(default_factory=list)
