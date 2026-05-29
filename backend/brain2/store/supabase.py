"""SupabaseStore — the cloud-tier Store, a faithful wrapper over today's code.

    SupabaseStore(access_token?) ──► {service_client, user_client(token)} ──► Postgres

This introduces no new SQL: every query/RPC here is copied verbatim from the
engine's current call sites (preamble, findings/service, capture, explore,
synopsis, tenancy, monitoring) so flipping those sites to the Store later is a
no-op. See each method's docstring for the source it mirrors.

**Client-selection decision.** The existing code splits clients by intent:
user-scoped writes/reads on findings go through `user_client(access_token)` so
RLS is authoritative, while reads, tenancy find-or-create, synopsis, exploration
rows and monitoring use the `service_client()` (with explicit org/kb scoping).
To keep this a low-risk wrapper we take `access_token` at construction and pick
the client *per method exactly as the original* did — RLS-scoped finding ops use
`_user` (the token client when a token is present, else the service client as a
single-user fallback), everything else uses `service_client()`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from supabase import Client

from brain2.agent.synopsis import load_synopsis as _load_synopsis
from brain2.clients.supabase import service_client, user_client
from brain2.interfaces.mcp.tenancy import (
    _find_or_create,
    _login,
    _org_for,
)
from brain2.monitoring.recorder import record_access as _record_access

# Column lists copied from findings/service.py — keep in lockstep.
_FINDING_COLS = "id, title, content, category, confidence, tags, provenance, created_at"
_FINDING_LIST_COLS = "id, title, category, confidence, tags, created_at"

LIST_DEFAULT_LIMIT = 20
LIST_MAX_LIMIT = 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseStore:
    """Store backed by Supabase. `access_token` selects RLS-scoped finding ops."""

    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token

    # --- client selection ----------------------------------------------------

    def _user(self) -> Client:
        """RLS-scoped client for finding reads/writes; service client when no token."""
        return user_client(self.access_token) if self.access_token else service_client()

    # --- findings — hot path -------------------------------------------------

    async def match_findings(
        self,
        kb_id: str,
        query_embedding: list[float],
        match_count: int,
        min_similarity: float,
    ) -> list[dict]:
        """Mirrors agent/preamble.py select_preamble — the match_findings RPC.

        Runs against the service client (the preamble path already uses a service
        client for this read). Rows carry a `similarity` field."""
        res = service_client().rpc(
            "match_findings",
            {
                "query_embedding": query_embedding,
                "match_kb_id": kb_id,
                "match_count": match_count,
                "min_similarity": min_similarity,
            },
        ).execute()
        return res.data or []

    async def insert_findings(self, rows: list[dict]) -> list[str]:
        """Insert already-embedded finding rows; return ids in order.

        Mirrors capture/service.py + findings/ingest.py: rows are built and
        embedded by the caller and written through the user-scoped client."""
        if not rows:
            return []
        inserted = self._user().table("findings").insert(rows).execute()
        return [r["id"] for r in (inserted.data or [])]

    def get_finding(self, kb_id: str, finding_id: str) -> dict:
        """Mirrors findings/service.py get_finding."""
        row = (
            self._user()
            .table("findings")
            .select(_FINDING_COLS)
            .eq("kb_id", kb_id)
            .eq("id", finding_id)
            .limit(1)
            .execute()
        ).data
        if not row:
            raise RuntimeError("finding not found")
        return row[0]

    def list_findings(
        self, kb_id: str, category: str | None = None, limit: int | None = None
    ) -> dict:
        """Mirrors findings/service.py list_findings."""
        n = min(limit or LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT)
        q = (
            self._user()
            .table("findings")
            .select(_FINDING_LIST_COLS)
            .eq("kb_id", kb_id)
        )
        if category:
            q = q.eq("category", category)
        rows = q.order("created_at", desc=True).limit(n).execute().data or []
        return {"count": len(rows), "findings": rows}

    def delete_finding(self, kb_id: str, finding_id: str) -> dict:
        """Mirrors findings/service.py delete_finding."""
        self._user().table("findings").delete().eq("kb_id", kb_id).eq(
            "id", finding_id
        ).execute()
        return {"deleted": finding_id}

    def count_findings(self, kb_id: str) -> int:
        """Exact finding count for `kb_id` via a count="exact" head query.

        Mirrors kbs/service.py kb_stats: a `count="exact"` select scoped to
        `kb_id`, limited to one row (the count rides on the result, not the rows)."""
        return (
            self._user()
            .table("findings")
            .select("id", count="exact")
            .eq("kb_id", kb_id)
            .limit(1)
            .execute()
        ).count or 0

    # --- synopsis spine ------------------------------------------------------

    def load_synopsis(self, kb_id: str) -> dict | None:
        """Reuses agent/synopsis.py load_synopsis against the service client."""
        return _load_synopsis(service_client(), kb_id)

    def upsert_synopsis(
        self, kb_id: str, content: list[dict], finding_count: int, model: str
    ) -> None:
        """Mirrors the kb_synopsis upsert in agent/synopsis.py maybe_rebuild_synopsis.

        `org_id` is resolved from the kb row to satisfy the table's not-null
        column; the upsert conflicts on kb_id (one current row per KB). `model`
        records the synopsis-builder model for provenance (a not-null-able
        column the original write set)."""
        sb = service_client()
        kb = sb.table("kbs").select("org_id").eq("id", kb_id).limit(1).execute().data
        if not kb:
            raise RuntimeError(f"kb {kb_id} not found — cannot upsert synopsis")
        org_id = kb[0]["org_id"]
        sb.table("kb_synopsis").upsert(
            {
                "org_id": org_id,
                "kb_id": kb_id,
                "content": content,
                "finding_count_at_build": finding_count,
                "model": model,
                "built_at": _now_iso(),
            },
            on_conflict="kb_id",
        ).execute()

    # --- exploration row lifecycle -------------------------------------------

    def create_exploration(self, org_id: str, kb_id: str, prompt: str) -> str:
        """Mirrors the explorations insert in api/explore.py start_explore."""
        row = (
            service_client()
            .table("explorations")
            .insert(
                {
                    "org_id": org_id,
                    "kb_id": kb_id,
                    "prompt": prompt,
                    "status": "pending",
                    "started_at": _now_iso(),
                }
            )
            .execute()
        )
        return row.data[0]["id"]

    def update_exploration(self, exploration_id: str, **patch) -> None:
        """Mirrors the explorations update calls in api/explore.py."""
        service_client().table("explorations").update(patch).eq(
            "id", exploration_id
        ).execute()

    def get_exploration(self, exploration_id: str) -> dict | None:
        """Mirrors the explorations read in api/explore.py explore_status."""
        rows = (
            service_client()
            .table("explorations")
            .select("id, status, finding_ids, completed_at, error")
            .eq("id", exploration_id)
            .limit(1)
            .execute()
        ).data
        return rows[0] if rows else None

    # --- tenancy — find-or-create by name ------------------------------------

    def resolve_project(self, name: str, *, create: bool) -> tuple[str, str]:
        """Mirrors interfaces/mcp/tenancy.py resolve_project_id → (org_id, project_id)."""
        user_id, _ = _login()
        org_id = _org_for(user_id)
        sb = service_client()
        pid = _find_or_create(
            sb,
            "projects",
            {"org_id": org_id, "name": name},
            {"org_id": org_id, "name": name},
            create,
        )
        return org_id, pid

    def resolve_kb(self, org_id: str, project_id: str, name: str, *, create: bool) -> str:
        """Mirrors the kbs find-or-create in interfaces/mcp/tenancy.py resolve_tenant."""
        sb = service_client()
        return _find_or_create(
            sb,
            "kbs",
            {"org_id": org_id, "project_id": project_id, "name": name},
            {"org_id": org_id, "project_id": project_id, "name": name},
            create,
        )

    # --- monitoring — best-effort --------------------------------------------

    async def record_access(
        self,
        *,
        org_id: str,
        kb_id: str,
        surface: str,
        targets,
        query_text: str | None = None,
    ) -> None:
        """Delegates to monitoring/recorder.py record_access — never raises.

        `targets` is a sequence of monitoring.recorder.Target. Delegating keeps
        the access_events row shape in lockstep with the canonical writer and
        preserves its best-effort (never-raises) contract."""
        await _record_access(
            org_id=org_id,
            kb_id=kb_id,
            surface=surface,
            targets=targets,
            query_text=query_text,
            sb=service_client(),
        )
