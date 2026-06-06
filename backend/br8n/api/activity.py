"""GET /v1/activity/* — read the cross-repo activity knowledge graph.

    /v1/activity/graph   subgraph (semantic `q`, optional `repo`)
    /v1/activity/stats   totals + hotspots (most-touched repos/files/tasks)

The graph is populated automatically on every capture (see
``knowledge_graph.activity``). These endpoints are read-only and resolve the
caller's reserved activity KB; they return empty-but-well-formed shapes before
any activity exists. Auth mirrors the rest of ``/v1`` (no-op on the local tier).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from br8n.agent.state import Principal
from br8n.api.auth import require_principal
from br8n.knowledge_graph.activity import activity_stats, query_activity

router = APIRouter(prefix="/v1/activity", dependencies=[Depends(require_principal)])


class GraphResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    summary: str


class StatsResponse(BaseModel):
    node_count: int
    edge_count: int
    by_type: dict[str, int]
    by_relation: dict[str, int]
    hotspots: dict[str, list[dict]]


@router.get("/graph", response_model=GraphResponse)
async def graph(
    q: str | None = Query(default=None, description="Semantic seed query"),
    repo: str | None = Query(default=None, description="Filter to one repository"),
    principal: Principal = Depends(require_principal),
) -> GraphResponse:
    """Return a slice of the activity graph — semantically seeded by `q`, or the
    whole (capped) graph when `q` is omitted; optionally filtered to one `repo`."""
    result = await query_activity(q, repo=repo, access_token=principal.access_token, org_id=principal.org_id)
    return GraphResponse(**result)


@router.get("/stats", response_model=StatsResponse)
async def stats(principal: Principal = Depends(require_principal)) -> StatsResponse:
    """Graph totals + hotspots (most-touched repos/files/tasks by edge degree)."""
    return StatsResponse(**activity_stats(access_token=principal.access_token, org_id=principal.org_id))
