"""HTTP auth for the brain2 REST API.

**Tier-aware.** The check forks on the active backend:

  * **local (free) tier** — no auth. The free tier runs a uvicorn bound to
    ``127.0.0.1`` for the single local user (no account, no Supabase). There is
    no key to share and no remote attacker reachable, so requiring a Bearer token
    would only friction the one trusted caller on the loopback interface. This
    is safe *only* because the local server binds to 127.0.0.1 (see docs); do
    not expose the local-tier app on a public interface.
  * **cloud (paid) tier** — pre-shared API key in ``Authorization: Bearer``,
    matched against ``BRAIN2_API_KEY`` (configured in the VS Code extension).

The key is validated here; tenant resolution (project → KB) happens
inside each endpoint using the same GoTrue login as the MCP server.
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from brain2.store import active_backend

_bearer = HTTPBearer(auto_error=False)


def _configured_key() -> str:
    key = os.getenv("BRAIN2_API_KEY", "")
    if not key:
        raise RuntimeError("BRAIN2_API_KEY is not set — set it in your .env file")
    return key


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    """FastAPI dependency: validates the Bearer token against BRAIN2_API_KEY.

    No-op on the local tier (localhost-only, single user, no key). Returns
    before touching ``_configured_key()`` so local users need not set
    ``BRAIN2_API_KEY``.
    """
    if active_backend() == "local":
        return
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if not secrets.compare_digest(credentials.credentials, _configured_key()):
        raise HTTPException(status_code=401, detail="Invalid API key")
