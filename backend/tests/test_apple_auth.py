from fastapi.testclient import TestClient

import brain2.api.apple_auth as mod
from brain2.api.main import create_app


class _Session:
    access_token = "acc"
    refresh_token = "ref"
    expires_in = 3600
    expires_at = 1234


class _User:
    id = "user-apple-1"


class _Resp:
    session = _Session()
    user = _User()


def test_apple_exchange_returns_session(monkeypatch):
    monkeypatch.setattr(mod, "_apple_sign_in", lambda token, nonce: _Resp())
    client = TestClient(create_app())
    r = client.post("/v1/auth/apple", json={"identity_token": "tok", "nonce": "n"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] == "acc" and body["user_id"] == "user-apple-1"
    assert body["refresh_token"] == "ref"


def test_apple_exchange_bad_token_401(monkeypatch):
    def boom(token, nonce):
        raise mod.AppleAuthError("bad")
    monkeypatch.setattr(mod, "_apple_sign_in", boom)
    client = TestClient(create_app())
    r = client.post("/v1/auth/apple", json={"identity_token": "x", "nonce": "n"})
    assert r.status_code == 401


async def _fake_refresh(refresh_token):
    return {
        "access_token": "new-acc",
        "refresh_token": "new-ref",
        "expires_in": 3600,
        "expires_at": 9999,
        "user": {"id": "user-apple-1"},
    }


def test_refresh_returns_rotated_session(monkeypatch):
    monkeypatch.setattr(mod, "_refresh_session", _fake_refresh)
    client = TestClient(create_app())
    r = client.post("/v1/auth/refresh", json={"refresh_token": "old-ref"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] == "new-acc" and body["refresh_token"] == "new-ref"


def test_refresh_bad_token_401(monkeypatch):
    async def boom(refresh_token):
        raise mod.AppleAuthError("nope")
    monkeypatch.setattr(mod, "_refresh_session", boom)
    client = TestClient(create_app())
    r = client.post("/v1/auth/refresh", json={"refresh_token": "x"})
    assert r.status_code == 401
