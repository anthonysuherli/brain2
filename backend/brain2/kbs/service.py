"""KB CRUD + stats over the `kbs` table (and read-only over `findings`/`explorations`).

    project_id ──► kbs row(s)                       create / get / delete
    project_id ──► projects.default_kb_id           set_default_kb
    kb_id      ──► findings + explorations aggregate kb_stats

Pure data functions over a Supabase client; the MCP layer resolves tenancy and
passes `org_id`/`project_id`/`kb_id`. Every query stays scoped to `org_id` (the
`mcp/tenancy.py` invariant — service client, no RLS in the loop).
"""

from __future__ import annotations

from supabase import Client

_COLS = "id, name, description, published, created_at"

# kb_stats fetches finding (category, confidence) client-side to aggregate — no
# GROUP BY over PostgREST without an RPC. Capped; flagged when the cap truncates.
_STATS_SCAN_CAP = 2000


def create_kb(
    sb: Client,
    org_id: str,
    project_id: str,
    name: str,
    description: str | None = None,
) -> dict:
    """Find-or-create by (project_id, name). Returns `{created, kb}`. Mirrors
    `tenancy.resolve_tenant`'s find-or-create (no unique constraint exists)."""
    existing = (
        sb.table("kbs")
        .select(_COLS)
        .eq("org_id", org_id)
        .eq("project_id", project_id)
        .eq("name", name)
        .limit(1)
        .execute()
    ).data
    if existing:
        return {"created": False, "kb": existing[0]}
    insert = {"org_id": org_id, "project_id": project_id, "name": name}
    if description is not None:
        insert["description"] = description
    row = sb.table("kbs").insert(insert).execute().data
    if not row:
        raise RuntimeError("kb insert returned no row")
    return {"created": True, "kb": row[0]}


def get_kb(sb: Client, org_id: str, kb_id: str) -> dict:
    row = (
        sb.table("kbs").select(_COLS).eq("org_id", org_id).eq("id", kb_id).limit(1).execute()
    ).data
    if not row:
        raise RuntimeError("kb not found")
    return row[0]


def update_kb(
    sb: Client,
    org_id: str,
    kb_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict:
    """Patch name and/or description. No-op patch returns the current row.

    Mirrors `projects.service.update_project`. `kb_id` is already org-scoped by
    the caller's tenant resolution; the explicit `.eq("org_id", ...)` is kept as
    the cross-org invariant (service client, no RLS in the loop)."""
    patch: dict[str, str] = {}
    if name is not None:
        patch["name"] = name
    if description is not None:
        patch["description"] = description
    if not patch:
        return get_kb(sb, org_id, kb_id)
    row = (sb.table("kbs").update(patch).eq("org_id", org_id).eq("id", kb_id).execute()).data
    if not row:
        raise RuntimeError("kb not found")
    return row[0]


def delete_kb(sb: Client, org_id: str, kb_id: str) -> dict:
    """Delete the KB. Findings/explorations/synopsis cascade. If this KB was a
    project's default, the deferred FK nulls `projects.default_kb_id`."""
    sb.table("kbs").delete().eq("org_id", org_id).eq("id", kb_id).execute()
    return {"deleted": kb_id}


def set_default_kb(sb: Client, org_id: str, project_id: str, kb_id: str) -> dict:
    """Point `projects.default_kb_id` at this KB."""
    row = (
        sb.table("projects")
        .update({"default_kb_id": kb_id})
        .eq("org_id", org_id)
        .eq("id", project_id)
        .execute()
    ).data
    if not row:
        raise RuntimeError("project not found")
    return {"project_id": project_id, "default_kb_id": kb_id}


def kb_stats(sb: Client, kb_id: str) -> dict:
    """Finding count, counts by category, mean confidence, last exploration.

    `kb_id` is already org-scoped by the caller's tenant resolution."""
    total = (
        sb.table("findings").select("id", count="exact").eq("kb_id", kb_id).limit(1).execute()
    ).count or 0

    scanned = (
        sb.table("findings")
        .select("category, confidence")
        .eq("kb_id", kb_id)
        .limit(_STATS_SCAN_CAP)
        .execute()
    ).data or []
    rows = [r for r in scanned if isinstance(r, dict)]

    by_category: dict[str, int] = {}
    confidences: list[float] = []
    for r in rows:
        cat = r.get("category") or "uncategorized"
        by_category[cat] = by_category.get(cat, 0) + 1
        c = r.get("confidence")
        if c is not None:
            confidences.append(float(c))

    last = (
        sb.table("explorations")
        .select("id, prompt, status, created_at")
        .eq("kb_id", kb_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    return {
        "finding_count": total,
        "by_category": by_category,
        "mean_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "last_exploration": (last or [None])[0],
        "category_counts_truncated": total > len(rows),
    }
