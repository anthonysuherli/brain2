"""require_api_key is tier-aware: no-op local, Bearer-validated cloud.

These unit-test the dependency directly (no app needed). Env is set via
monkeypatch so global state is restored; get_settings is lru_cached, so we clear
it around any path that may sniff Supabase creds.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import br8n.config as config
from br8n.api.auth import require_api_key


def _reset_settings_cache() -> None:
    config.get_settings.cache_clear()


def test_local_tier_skips_auth_no_header(monkeypatch):
    """Local tier: missing Authorization header must NOT raise (and must not touch
    BR8N_API_KEY)."""
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.delenv("BR8N_API_KEY", raising=False)
    _reset_settings_cache()
    try:
        assert require_api_key(credentials=None) is None
    finally:
        _reset_settings_cache()


def test_cloud_tier_missing_bearer_raises_401(monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "cloud")
    monkeypatch.setenv("BR8N_API_KEY", "secret-key")
    _reset_settings_cache()
    try:
        with pytest.raises(HTTPException) as exc:
            require_api_key(credentials=None)
        assert exc.value.status_code == 401
    finally:
        _reset_settings_cache()


def test_cloud_tier_invalid_key_raises_401(monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "cloud")
    monkeypatch.setenv("BR8N_API_KEY", "secret-key")
    _reset_settings_cache()
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-key")
    try:
        with pytest.raises(HTTPException) as exc:
            require_api_key(credentials=creds)
        assert exc.value.status_code == 401
    finally:
        _reset_settings_cache()


def test_cloud_tier_valid_key_passes(monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "cloud")
    monkeypatch.setenv("BR8N_API_KEY", "secret-key")
    _reset_settings_cache()
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret-key")
    try:
        assert require_api_key(credentials=creds) is None
    finally:
        _reset_settings_cache()


def test_run_local_tier_refuses_nonloopback_host(monkeypatch):
    """Defense-in-depth: run() must refuse a non-loopback bind on the auth-less
    local tier rather than silently exposing an unauthenticated API."""
    from br8n.api.main import run

    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_HOST", "0.0.0.0")
    _reset_settings_cache()
    try:
        with pytest.raises(SystemExit) as exc:
            run()
        assert "loopback" in str(exc.value)
    finally:
        _reset_settings_cache()
