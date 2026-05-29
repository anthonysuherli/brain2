"""Finding read/delete — thin pass-throughs over the active `Store`.

    ctx (kb_id + access_token) ──► get_store(token) ──► findings rows

These wrap `Store.get_finding` / `list_findings` / `delete_finding`, scoping
every call to `ctx.kb_id` and threading `ctx.access_token` so the cloud tier
keeps its RLS-scoped user client. The local tier ignores the token (single
user). Public names are preserved for callers that import this module.
"""

from __future__ import annotations

from brain2.agent.state import TenantContext
from brain2.clients.supabase import user_client
from brain2.store import get_store

LIST_DEFAULT_LIMIT = 20
LIST_MAX_LIMIT = 100


def get_finding(ctx: TenantContext, finding_id: str) -> dict:
    return get_store(ctx.access_token).get_finding(ctx.kb_id, finding_id)


def list_findings(
    ctx: TenantContext, *, category: str | None = None, limit: int | None = None
) -> dict:
    """Most-recent findings, optionally filtered by category."""
    return get_store(ctx.access_token).list_findings(
        ctx.kb_id, category=category, limit=limit
    )


def delete_finding(ctx: TenantContext, finding_id: str) -> dict:
    """Delete one finding from the active KB."""
    return get_store(ctx.access_token).delete_finding(ctx.kb_id, finding_id)


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
