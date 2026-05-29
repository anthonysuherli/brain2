"""Store: the engine's persistence seam.

`Store` is the protocol; `SupabaseStore` is the cloud implementation. `get_store`
is the factory the engine calls. Backend selection by env var (free/local SQLite
vs cloud Supabase) lands in a later task — for now this always returns Supabase.
"""

from __future__ import annotations

from brain2.store.base import Store
from brain2.store.sqlite import SQLiteStore
from brain2.store.supabase import SupabaseStore

__all__ = ["Store", "SupabaseStore", "SQLiteStore", "get_store"]


def get_store(access_token: str | None = None) -> Store:
    """Return the active Store. Today: always SupabaseStore (cloud tier)."""
    return SupabaseStore(access_token)
