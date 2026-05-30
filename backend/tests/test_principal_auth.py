from __future__ import annotations
import time
import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import brain2.config as config
import brain2.api.auth as auth

SECRET = "test-jwt-secret"

def _reset():
    config.get_settings.cache_clear()

def _token(sub="user-1", aud="authenticated", exp_delta=3600):
    return jwt.encode({"sub": sub, "aud": aud, "exp": int(time.time()) + exp_delta}, SECRET, algorithm="HS256")

def _creds(tok):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok)

def test_local_tier_returns_local_principal(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    _reset()
    try:
        p = auth.require_principal(credentials=None)
        assert (p.user_id, p.org_id, p.access_token) == ("local", "local", "")
    finally:
        _reset()

def test_cloud_valid_jwt_yields_principal(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "cloud")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "_org_for_or_create", lambda uid: f"org-of-{uid}")
    _reset()
    try:
        p = auth.require_principal(credentials=_creds(_token("user-1")))
        assert p.user_id == "user-1" and p.org_id == "org-of-user-1"
        assert p.access_token
    finally:
        _reset()

def test_cloud_expired_jwt_401(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "cloud")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "_org_for_or_create", lambda uid: "org")
    _reset()
    try:
        with pytest.raises(HTTPException) as e:
            auth.require_principal(credentials=_creds(_token(exp_delta=-10)))
        assert e.value.status_code == 401
    finally:
        _reset()

def test_cloud_wrong_secret_401(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "cloud")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "_org_for_or_create", lambda uid: "org")
    _reset()
    bad = jwt.encode({"sub": "u", "aud": "authenticated", "exp": int(time.time()) + 60}, "other-secret", algorithm="HS256")
    try:
        with pytest.raises(HTTPException) as e:
            auth.require_principal(credentials=_creds(bad))
        assert e.value.status_code == 401
    finally:
        _reset()

def test_cloud_missing_bearer_401(monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "cloud")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    _reset()
    try:
        with pytest.raises(HTTPException) as e:
            auth.require_principal(credentials=None)
        assert e.value.status_code == 401
    finally:
        _reset()
