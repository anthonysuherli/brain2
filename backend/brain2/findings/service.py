"""Finding read/delete over the `findings` table.

    ctx (kb_id + access_token) ──► user_client ──► findings rows

Reads/deletes go through the **user-scoped** client so RLS is authoritative —
matching `tools/explore.py`'s recall path and CLAUDE.md's convention for
user-facing finding access. All queries are pinned to `ctx.kb_id`.
"""

from __future__ import annotations

from brain2.agent.state import TenantContext
from brain2.clients.supabase import user_client

_COLS = "id, title, content, category, confidence, tags, provenance, created_at"

LIST_DEFAULT_LIMIT = 20
LIST_MAX_LIMIT = 100


def get_finding(ctx: TenantContext, finding_id: str) -> dict:
    row = (
        user_client(ctx.access_token)
        .table("findings")
        .select(_COLS)
        .eq("kb_id", ctx.kb_id)
        .eq("id", finding_id)
        .limit(1)
        .execute()
    ).data
    if not row:
        raise RuntimeError("finding not found")
    return row[0]


def list_findings(
    ctx: TenantContext, *, category: str | None = None, limit: int | None = None
) -> dict:
    """Most-recent findings, optionally filtered by category."""
    n = min(limit or LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT)
    q = (
        user_client(ctx.access_token)
        .table("findings")
        .select("id, title, category, confidence, tags, created_at")
        .eq("kb_id", ctx.kb_id)
    )
    if category:
        q = q.eq("category", category)
    rows = q.order("created_at", desc=True).limit(n).execute().data or []
    return {"count": len(rows), "findings": rows}


def delete_finding(ctx: TenantContext, finding_id: str) -> dict:
    """Delete one finding from the active KB (RLS-scoped)."""
    user_client(ctx.access_token).table("findings").delete().eq("kb_id", ctx.kb_id).eq(
        "id", finding_id
    ).execute()
    return {"deleted": finding_id}


def findings_for_report(ctx: TenantContext, *, limit: int = 200) -> list[dict]:
    """Findings (with `content`) for report generation, highest-confidence first.

    Unlike `list_findings` (recency-ordered, no content), the report authoring
    pass needs the body text and wants the strongest evidence first; `limit` is
    a safety cap over the whole KB."""
    return (
        user_client(ctx.access_token)
        .table("findings")
        .select("id, title, content, category, confidence")
        .eq("kb_id", ctx.kb_id)
        .order("confidence", desc=True)
        .limit(limit)
        .execute()
    ).data or []
