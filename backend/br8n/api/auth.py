"""HTTP auth for the br8n REST API.

**Tier-aware.** The check forks on the active backend:

  * **local (free) tier** — no auth. The free tier runs a uvicorn bound to
    ``127.0.0.1`` for the single local user (no account, no Supabase). There is
    no key to share and no remote attacker reachable, so requiring a Bearer token
    would only friction the one trusted caller on the loopback interface. This
    is safe *only* because the local server binds to 127.0.0.1 (see docs); do
    not expose the local-tier app on a public interface.
  * **cloud (paid) tier** — pre-shared API key in ``Authorization: Bearer``,
    matched against ``BR8N_API_KEY`` (configured in the VS Code extension).

The key is validated here; tenant resolution (project → KB) happens
inside each endpoint using the same GoTrue login as the MCP server.
"""

from __future__ import annotations

import os
import secrets

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from br8n.agent.state import Principal
from br8n.config import get_settings
from br8n.interfaces.mcp.tenancy import _org_for_or_create
from br8n.store import active_backend

_bearer = HTTPBearer(auto_error=False)


def _configured_key() -> str:
    key = os.getenv("BR8N_API_KEY", "")
    if not key:
        raise RuntimeError("BR8N_API_KEY is not set — set it in your .env file")
    return key


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    """FastAPI dependency: validates the Bearer token against BR8N_API_KEY.

    No-op on the local tier (localhost-only, single user, no key). Returns
    before touching ``_configured_key()`` so local users need not set
    ``BR8N_API_KEY``.
    """
    if active_backend() == "local":
        return
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if not secrets.compare_digest(credentials.credentials, _configured_key()):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _verify_supabase_jwt(token: str) -> str:
    """Return the user id (sub) from a Supabase GoTrue access token, or raise 401."""
    secret = get_settings().supabase_jwt_secret
    if not secret:
        raise RuntimeError("SUPABASE_JWT_SECRET is not set — required for the cloud tier")
    try:
        claims = jwt.decode(
            token, secret, algorithms=["HS256"],
            audience="authenticated", options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return claims["sub"]


def require_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> Principal:
    """FastAPI dependency: the authenticated caller. Local tier = single user."""
    if active_backend() == "local":
        return Principal(user_id="local", org_id="local", access_token="")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = credentials.credentials
    user_id = _verify_supabase_jwt(token)
    return Principal(user_id=user_id, org_id=_org_for_or_create(user_id), access_token=token)
