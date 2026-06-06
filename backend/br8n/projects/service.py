"""Project CRUD over the `projects` table.

    org_id (resolved by caller) ──► projects row(s) {id,name,description,default_kb_id}

Pure data functions over a Supabase client. The MCP layer resolves the tenant's
`org_id` from the authenticated user and passes it in; **every query here stays
scoped to that `org_id`** — the same load-bearing invariant as `mcp/tenancy.py`.
No RLS in the loop (service client), so the explicit `.eq("org_id", ...)` is what
keeps reads/writes from leaking across orgs. Don't drop it.
"""

from __future__ import annotations

from supabase import Client

_COLS = "id, name, description, default_kb_id, created_at"


def _by_name(sb: Client, org_id: str, name: str) -> dict | None:
    res = (
        sb.table("projects").select(_COLS).eq("org_id", org_id).eq("name", name).limit(1).execute()
    )
    return (res.data or [None])[0]


def create_project(sb: Client, org_id: str, name: str, description: str | None = None) -> dict:
    """Find-or-create by name (idempotent). Returns `{created, project}`.

    `projects` has no unique (org_id, name) constraint, so a pre-existing row is
    reused rather than duplicated — matching `tenancy.resolve_project_id`."""
    existing = _by_name(sb, org_id, name)
    if existing:
        return {"created": False, "project": existing}
    insert = {"org_id": org_id, "name": name}
    if description is not None:
        insert["description"] = description
    row = sb.table("projects").insert(insert).execute().data
    if not row:
        raise RuntimeError("project insert returned no row")
    return {"created": True, "project": row[0]}


def get_project(sb: Client, org_id: str, project_id: str) -> dict:
    """Project row + its KBs (id/name/published)."""
    proj = (
        sb.table("projects")
        .select(_COLS)
        .eq("org_id", org_id)
        .eq("id", project_id)
        .limit(1)
        .execute()
    ).data
    if not proj:
        raise RuntimeError("project not found")
    kbs = (
        sb.table("kbs")
        .select("id, name, description, published")
        .eq("org_id", org_id)
        .eq("project_id", project_id)
        .order("created_at")
        .execute()
    ).data or []
    return {"project": proj[0], "kbs": kbs}


def update_project(
    sb: Client,
    org_id: str,
    project_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict:
    """Patch name and/or description. No-op patch returns the current row."""
    patch: dict[str, str] = {}
    if name is not None:
        patch["name"] = name
    if description is not None:
        patch["description"] = description
    if not patch:
        return get_project(sb, org_id, project_id)["project"]
    row = (
        sb.table("projects").update(patch).eq("org_id", org_id).eq("id", project_id).execute()
    ).data
    if not row:
        raise RuntimeError("project not found")
    return row[0]


def delete_project(sb: Client, org_id: str, project_id: str) -> dict:
    """Delete the project. KBs/findings cascade (ON DELETE CASCADE in schema)."""
    sb.table("projects").delete().eq("org_id", org_id).eq("id", project_id).execute()
    return {"deleted": project_id}
