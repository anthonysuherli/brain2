"""Supabase client factories (adapted from Divergence)."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from brain2.config import get_settings


@lru_cache(maxsize=1)
def service_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def user_client(access_token: str) -> Client:
    """Per-request client scoped to the user's JWT. NOT cached."""
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client
