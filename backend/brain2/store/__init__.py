"""Store: the engine's persistence seam + backend selection.

`Store` is the protocol; `SupabaseStore` (cloud) and `SQLiteStore` (free/local)
are the two implementations. `get_store()` is the factory the engine calls.

Backend selection (in order):
  1. ``BRAIN2_BACKEND`` env var — ``"local"`` or ``"cloud"`` (explicit override);
  2. otherwise ``"cloud"`` iff the Supabase creds are present, else ``"local"``.

Caching: the local SQLite store holds a long-lived connection, so it is cached
as a module-level singleton keyed by db_path (one connection reused across
calls; a different ``BRAIN2_DB_PATH`` — as tests use — gets its own store). The
cloud store is built fresh every call: it carries a per-request ``access_token``
(RLS scope), so caching it would be wrong across users. This mirrors today's
behaviour where ``user_client(token)`` is created per request.
"""

from __future__ import annotations

import os

from brain2.config import get_settings
from brain2.store.base import Store
from brain2.store.sqlite import SQLiteStore, _default_db_path
from brain2.store.supabase import SupabaseStore

__all__ = ["Store", "SupabaseStore", "SQLiteStore", "get_store", "active_backend"]

# Local stores cached by db_path so the SQLite connection is reused.
_local_stores: dict[str, SQLiteStore] = {}


def _has_cloud_creds() -> bool:
    """True iff the Supabase env vars needed for the cloud tier are present."""
    s = get_settings()
    return bool(s.supabase_url and s.supabase_service_role_key)


def active_backend() -> str:
    """The selected backend name — ``"local"`` or ``"cloud"``.

    Single source of truth for selection, shared by `get_store` and the tenancy
    fork (local skips GoTrue login). ``BRAIN2_BACKEND`` overrides creds-sniffing.
    """
    backend = os.getenv("BRAIN2_BACKEND")
    if not backend:
        backend = "cloud" if _has_cloud_creds() else "local"
    return backend


def get_store(access_token: str | None = None) -> Store:
    """Return the active Store for this request.

    Local: a cached SQLiteStore (connection reused). Cloud: a fresh
    SupabaseStore bound to ``access_token`` for RLS-scoped finding ops.
    """
    if active_backend() == "local":
        path = _default_db_path()
        store = _local_stores.get(path)
        if store is None:
            store = SQLiteStore(path)
            _local_stores[path] = store
        return store
    return SupabaseStore(access_token)
