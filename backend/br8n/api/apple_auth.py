"""POST /v1/auth/apple + /v1/auth/refresh — Apple sign-in + GoTrue refresh.

Delegates Apple-token verification + user provisioning to Supabase via
sign_in_with_id_token; refresh proxies GoTrue so the anon key stays server-side.
Both endpoints are UN-gated (they mint/rotate the session).
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client

from br8n.config import get_settings

router = APIRouter(prefix="/v1/auth")


class AppleAuthError(Exception):
    ...


class AppleExchangeRequest(BaseModel):
    identity_token: str
    nonce: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: int | None = None
    user_id: str


def _apple_sign_in(identity_token: str, nonce: str | None):
    s = get_settings()
    if not (s.supabase_url and s.supabase_anon_key):
        raise AppleAuthError("Supabase not configured")
    anon = create_client(s.supabase_url, s.supabase_anon_key)
    creds: dict = {"provider": "apple", "token": identity_token}
    if nonce:
        creds["nonce"] = nonce
    try:
        return anon.auth.sign_in_with_id_token(creds)
    except Exception as e:  # gotrue AuthApiError etc.
        raise AppleAuthError(str(e)) from e


@router.post("/apple", response_model=SessionResponse)
async def apple_exchange(body: AppleExchangeRequest) -> SessionResponse:
    try:
        res = _apple_sign_in(body.identity_token, body.nonce)
    except AppleAuthError as e:
        raise HTTPException(status_code=401, detail=f"Apple sign-in failed: {e}")
    sess = getattr(res, "session", None)
    user = getattr(res, "user", None)
    if not sess or not user:
        raise HTTPException(status_code=401, detail="No session from Supabase")
    return SessionResponse(
        access_token=sess.access_token,
        refresh_token=sess.refresh_token,
        expires_in=sess.expires_in,
        expires_at=getattr(sess, "expires_at", None),
        user_id=user.id,
    )


async def _refresh_session(refresh_token: str) -> dict:
    """Proxy GoTrue refresh; returns the raw token JSON. Keeps the anon key server-side."""
    s = get_settings()
    if not (s.supabase_url and s.supabase_anon_key):
        raise AppleAuthError("Supabase not configured")
    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.post(
            f"{s.supabase_url}/auth/v1/token",
            params={"grant_type": "refresh_token"},
            headers={"apikey": s.supabase_anon_key, "Content-Type": "application/json"},
            json={"refresh_token": refresh_token},
        )
    if resp.status_code != 200:
        raise AppleAuthError(f"refresh failed: {resp.status_code}")
    return resp.json()


@router.post("/refresh", response_model=SessionResponse)
async def refresh(body: RefreshRequest) -> SessionResponse:
    try:
        data = await _refresh_session(body.refresh_token)
    except AppleAuthError as e:
        raise HTTPException(status_code=401, detail=f"Refresh failed: {e}")
    user = data.get("user") or {}
    return SessionResponse(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=data.get("expires_in", 3600),
        expires_at=data.get("expires_at"),
        user_id=user.get("id", ""),
    )
