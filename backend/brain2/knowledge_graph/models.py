"""Graph data models — the carriers between extraction and the Store.

Ported from divergence's KG models (the only piece of that layer brain2 reuses).
``properties`` are free-form dicts; an ``embedding`` rides along on a node so the
Store can persist it for semantic subgraph seeding. Dedupe is by exact
``(type, label)`` at the Store, so these models stay pure data.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KGNode(BaseModel):
    """One entity. ``label`` is its canonical name; ``type`` its ontology class."""

    label: str = Field(description="Canonical name of the entity (e.g. 'brain2' or 'store/base.py')")
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
