"""Supabase client factories (adapted from Divergence)."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from brain2.config import get_settings

_NO_CREDS = (
    "cloud backend requires SUPABASE_* env vars "
    "(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY); "
    "set BRAIN2_BACKEND=local to use the SQLite tier instead"
)


@lru_cache(maxsize=1)
def service_client() -> Client:
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_service_role_key):
        raise RuntimeError(_NO_CREDS)
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def user_client(access_token: str) -> Client:
    """Per-request client scoped to the user's JWT. NOT cached."""
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_anon_key):
        raise RuntimeError(_NO_CREDS)
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client
