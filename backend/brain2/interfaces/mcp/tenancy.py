"""Resolve a TenantContext for the in-process MCP entry path.

    GoTrue login (configured MCP user)  ──► user_id + JWT
    service_client  ──► org (via membership) ──► project (by name) ──► kb (by name)

The JWT is a real GoTrue token, so user-scoped tools (`tap`, `search`) pass RLS.
Resolution is by *name* for delapan-style ergonomics; missing project/KB are
created on demand (toggle with `create=False`).

**Why the service client here, not the user client (a deliberate convention
deviation).** `/agent` resolves its KB through `user_client` so RLS gates the
lookup. This module instead uses the service client and an explicit
`.eq("org_id", ...)` filter on every query. Two reasons: (1) the org lookup hits
`org_members`, whose RLS has bitten this repo before (the recursion fixed in
`e056e29`) — the service client sidesteps that; (2) find-or-create by name is
simpler without RLS in the loop. **The load-bearing invariant is that every
query in this module stays scoped to the `org_id` derived from the authenticated
user's own membership.** A read added here without that `.eq("org_id", ...)`
would fail open (cross-org). Keep the filter, or move the read to `user_client`.
"""

from __future__ import annotations

import uuid

from supabase import Client, create_client

from brain2.agent.state import Principal, TenantContext
from brain2.clients.supabase import service_client
from brain2.config import get_settings


def _login() -> tuple[str, str]:
    s = get_settings()
    anon = create_client(s.supabase_url, s.supabase_anon_key)
    res = anon.auth.sign_in_with_password(
        {"email": s.mcp_user_email, "password": s.mcp_user_password}
    )
    if not res.session or not res.user:
        raise RuntimeError(
            "MCP user login failed — check DVG_MCP_USER_EMAIL / DVG_MCP_USER_PASSWORD "
            "and that the user exists (run scripts/seed_dev.py)."
        )
    return res.user.id, res.session.access_token


class _NoOrgError(RuntimeError):
    """The user has no org membership yet (distinct from real DB errors)."""


def _org_for(user_id: str) -> str:
    sb = service_client()
    om = sb.table("org_members").select("org_id").eq("user_id", user_id).limit(1).execute()
    if not om.data:
        raise _NoOrgError("no org for user — did the handle_new_user trigger run?")
    return om.data[0]["org_id"]


def _org_for_or_create(user_id: str) -> str:
    """Org for the user; provision one if the signup trigger didn't (first-seen)."""
    try:
        return _org_for(user_id)
    except _NoOrgError:
        sb = service_client()
        org = sb.table("orgs").insert(
            {"name": f"{user_id[:8]}'s workspace", "owner_user_id": user_id}
        ).execute().data
        if not org:
            raise RuntimeError("insert into orgs returned no row")
        org_id = org[0]["id"]
        sb.table("org_members").insert(
            {"org_id": org_id, "user_id": user_id, "role": "owner"}
        ).execute()
        return org_id


def _find_or_create(
    sb: Client, table: str, match: dict[str, str], insert: dict[str, object], create: bool
) -> str:
    q = sb.table(table).select("id")
    for k, v in match.items():
        q = q.eq(k, v)
    existing = q.limit(1).execute()
    if existing.data:
        return existing.data[0]["id"]
    if not create:
        raise RuntimeError(f"{table} {match!r} not found")
    inserted = sb.table(table).insert(insert).execute().data
    if not inserted:
        raise RuntimeError(f"insert into {table} returned no row")
    return inserted[0]["id"]


def resolve_project_id(project: str, *, create: bool = False) -> tuple[str, str]:
    """Return (org_id, project_id) for the named project, via the active Store."""
    from brain2.store import get_store

    return get_store().resolve_project(project, create=create)


def resolve_tenant(
    project: str, kb: str, *, principal: "Principal | None" = None, create: bool = True
) -> TenantContext:
    """Resolve a TenantContext by name, creating project/KB on demand.

    Identity fork:
      * local tier — single user, no auth (user_id="local", token="").
      * cloud + ``principal`` given — the request's verified identity drives
        tenancy; the principal's org_id is injected into the store so it does
        NOT re-login. This is the per-user request path.
      * cloud + no principal — legacy path: the configured MCP user login. Used
        by the in-process MCP server (single configured identity).
    `TenantContext`'s shape is identical on all paths.
    """
    from brain2.store import active_backend, get_store

    if active_backend() == "local":
        store = get_store()
        org_id, project_id = store.resolve_project(project, create=create)
        kb_id = store.resolve_kb(org_id, project_id, kb, create=create)
        return TenantContext("local", org_id, project_id, kb_id, str(uuid.uuid4()), "")

    if principal is not None:
        store = get_store(principal.access_token, org_id=principal.org_id)
        org_id, project_id = store.resolve_project(project, create=create)
        kb_id = store.resolve_kb(org_id, project_id, kb, create=create)
        return TenantContext(
            principal.user_id, org_id, project_id, kb_id, str(uuid.uuid4()), principal.access_token
        )

    # Legacy cloud path: configured MCP user login (unchanged behavior).
    user_id, token = _login()
    store = get_store(token)
    org_id, project_id = store.resolve_project(project, create=create)
    kb_id = store.resolve_kb(org_id, project_id, kb, create=create)
    return TenantContext(user_id, org_id, project_id, kb_id, str(uuid.uuid4()), token)


def resolve_store():
    """Org-scoped Store with no project/kb binding — for cross-repo reads.

    Same identity fork as ``resolve_tenant`` minus the project/kb resolution:
    local tier uses the single local store; legacy cloud logs the configured
    MCP user in for an RLS-scoped token. Used by the cross-repo ``brain2_projects``
    tool (the ``/brain2:pickup`` selector)."""
    from brain2.store import active_backend, get_store

    if active_backend() == "local":
        return get_store()
    _user_id, token = _login()
    return get_store(token)
