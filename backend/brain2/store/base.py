"""The Store protocol — the engine's single seam over persistence.

    engine ──► Store ──► {Supabase (cloud), SQLite (local)}

brain2 is split into a free/local tier (SQLite + sqlite-vec, single user, no
auth) and a paid/cloud tier (Supabase: Postgres + pgvector + GoTrue + RLS). The
engine talks to this protocol instead of any one backend so the two tiers share
one engine. Return shapes are plain dicts / lists of dicts matching today's
Supabase rows; no ORM, no backend-specific objects cross this boundary.

This file defines the contract ONLY. `supabase.py` is the cloud implementation;
the engine call sites are flipped to `get_store(...)` in a later task.
"""

from __future__ import annotations

from typing import Protocol


class Store(Protocol):
    """Persistence surface the engine depends on. Implementations are tier-specific."""

    # --- findings — hot path -------------------------------------------------

    async def match_findings(
        self,
        kb_id: str,
        query_embedding: list[float],
        match_count: int,
        min_similarity: float,
    ) -> list[dict]:
        """Vector-search findings in `kb_id`. Rows carry a `similarity` field."""
        ...

    async def insert_findings(self, rows: list[dict]) -> list[str]:
        """Insert already-embedded finding rows; return the new ids in order."""
        ...

    def get_finding(self, kb_id: str, finding_id: str) -> dict:
        """One finding scoped to `kb_id`. Raises if not found."""
        ...

    def list_findings(
        self, kb_id: str, category: str | None = None, limit: int | None = None
    ) -> dict:
        """Most-recent findings in `kb_id`. Returns {"count", "findings"}."""
        ...

    def delete_finding(self, kb_id: str, finding_id: str) -> dict:
        """Delete one finding from `kb_id`. Returns {"deleted": finding_id}."""
        ...

    # --- synopsis spine ------------------------------------------------------

    def load_synopsis(self, kb_id: str) -> dict | None:
        """Current synopsis row for `kb_id`, or None."""
        ...

    def upsert_synopsis(self, kb_id: str, content: list[dict], finding_count: int) -> None:
        """Write the KB's synopsis spine (one current row per KB)."""
        ...

    # --- exploration row lifecycle -------------------------------------------

    def create_exploration(self, org_id: str, kb_id: str, prompt: str) -> str:
        """Insert a pending exploration row; return its id."""
        ...

    def update_exploration(self, exploration_id: str, **patch) -> None:
        """Patch an exploration row (status / completed_at / finding_ids / error)."""
        ...

    def get_exploration(self, exploration_id: str) -> dict | None:
        """Read an exploration row, or None if missing."""
        ...

    # --- tenancy — find-or-create by name ------------------------------------

    def resolve_project(self, name: str, *, create: bool) -> tuple[str, str]:
        """Resolve the named project → (org_id, project_id)."""
        ...

    def resolve_kb(self, org_id: str, project_id: str, name: str, *, create: bool) -> str:
        """Resolve the named KB within (org_id, project_id) → kb_id."""
        ...

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
        """Append access events. Best-effort by contract — must never raise."""
        ...
