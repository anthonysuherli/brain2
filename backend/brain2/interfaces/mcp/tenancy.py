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

from brain2.agent.state import TenantContext
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


def _org_for(user_id: str) -> str:
    sb = service_client()
    om = sb.table("org_members").select("org_id").eq("user_id", user_id).limit(1).execute()
    if not om.data:
        raise RuntimeError("no org for MCP user — did the handle_new_user trigger run?")
    return om.data[0]["org_id"]


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


def resolve_tenant(project: str, kb: str, *, create: bool = True) -> TenantContext:
    """Resolve a TenantContext by name, creating project/KB on demand.

    **Backend fork.** Tenancy resolution goes through the active `Store`
    (`resolve_project` → (org_id, project_id), then `resolve_kb` → kb_id), so the
    local SQLite and cloud Supabase tiers share one shape. The only tier-specific
    step is *identity*: the cloud tier does a GoTrue login to obtain a real
    user_id + JWT (RLS scope) before resolving; the local tier is single-user and
    has no auth, so user_id="local", access_token="" (org_id="local" comes back
    from the store). `TenantContext`'s shape is identical on both paths.

    Two v0 assumptions on the cloud path, documented as known gaps:
      * name-resolution is single-flight — `projects`/`kbs` have no unique
        constraint on (org_id[, project_id], name), so concurrent first-touch
        of the same name can create duplicates; later resolves pick limit(1).
      * a fresh GoTrue login + org lookup runs on every call (no caching).
        Caching must add token expiry/refresh in the same change.
    """
    from brain2.store import active_backend, get_store

    store = get_store()
    if active_backend() == "local":
        # Single-user local tier: no GoTrue login. The store returns org_id="local".
        user_id, token = "local", ""
        org_id, project_id = store.resolve_project(project, create=create)
        kb_id = store.resolve_kb(org_id, project_id, kb, create=create)
    else:
        # Cloud tier: real GoTrue identity feeds RLS-scoped finding ops.
        # KNOWN FOLLOW-UP (cloud-only, non-blocking): this logs into GoTrue once
        # here for the token, and SupabaseStore.resolve_project logs in AGAIN
        # internally (+ a second org lookup). Same user/org, so it's a latency
        # regression, not a correctness bug. Fix alongside the login-caching work
        # noted above by threading the resolved (user_id, org_id) into the store.
        user_id, token = _login()
        org_id, project_id = store.resolve_project(project, create=create)
        kb_id = store.resolve_kb(org_id, project_id, kb, create=create)
    # thread_id is unused on this path (only POST /agent writes chat_messages).
    return TenantContext(
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
        kb_id=kb_id,
        thread_id=str(uuid.uuid4()),
        access_token=token,
    )
