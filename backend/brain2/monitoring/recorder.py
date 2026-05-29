"""Usage recording — the single write path into `access_events`.

    surface ──► record_access(org, kb, surface, targets[, api_key_id, query_text])
                                   └─► one batched insert into access_events

Best-effort and fire-and-forget by contract: a recording failure must NEVER
surface into the request path (a monitoring hiccup can't break a customer's
/v1 call or an MCP tool). Mirrors the api_key_usage insert in `api/auth.py` —
wrapped in try/except, service client, no RLS in the loop.

Batched on purpose: a /v1/graph returning 40 nodes + 60 edges is ONE insert of
100 rows, not 100 round-trips. `query_text` is the request-level q/focus, shared
across the batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from supabase import Client

from brain2.clients.supabase import service_client


@dataclass(frozen=True)
class Target:
    """One accessed thing. `target_id` is null for kb-level access (preamble)."""

    target_type: str  # 'node' | 'edge' | 'finding' | 'preamble'
    target_id: str | None = None


# --- target builders (keep call sites DRY across /v1 and MCP) ---------------


def targets_from_graph(graph: dict) -> list[Target]:
    """Nodes + edges of a read_graph / `/v1/graph` result → access targets."""
    out: list[Target] = []
    for n in graph.get("nodes") or []:
        if isinstance(n, dict) and n.get("id"):
            out.append(Target("node", str(n["id"])))
    for e in graph.get("edges") or []:
        if isinstance(e, dict) and e.get("id"):
            out.append(Target("edge", str(e["id"])))
    return out


def targets_from_findings(findings: Sequence[dict]) -> list[Target]:
    """Finding rows → access targets (skips rows without an id)."""
    return [
        Target("finding", str(f["id"])) for f in findings if isinstance(f, dict) and f.get("id")
    ]


PREAMBLE_TARGETS: list[Target] = [Target("preamble")]


# --- the write path ---------------------------------------------------------


async def record_access(
    *,
    org_id: str,
    kb_id: str,
    surface: str,
    targets: Sequence[Target],
    api_key_id: str | None = None,
    query_text: str | None = None,
    sb: Client | None = None,
) -> None:
    """Append one access event per target. Best-effort; never raises.

    `surface` is one of 'mcp' | 'v1_api' | 'agent'. `sb` is injectable for tests;
    defaults to the service client (the caller already resolved tenancy)."""
    if not targets:
        return
    rows = [
        {
            "org_id": org_id,
            "kb_id": kb_id,
            "target_type": t.target_type,
            "target_id": t.target_id,
            "surface": surface,
            "api_key_id": api_key_id,
            "query_text": query_text,
        }
        for t in targets
    ]
    try:
        client = sb or service_client()
        client.table("access_events").insert(rows).execute()
    except Exception:
        pass  # monitoring must not break the request path
