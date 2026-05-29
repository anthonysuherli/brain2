"""HTTP auth for the brain2 REST API.

Strategy (Phase 0): pre-shared API key in Authorization: Bearer.
The key is configured in the VS Code extension settings and matched
against BRAIN2_API_KEY in the environment.

The key is validated here; tenant resolution (project → KB) happens
inside each endpoint using the same GoTrue login as the MCP server.
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def _configured_key() -> str:
    key = os.getenv("BRAIN2_API_KEY", "")
    if not key:
        raise RuntimeError("BRAIN2_API_KEY is not set — set it in your .env file")
    return key


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    """FastAPI dependency: validates the Bearer token against BRAIN2_API_KEY."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if not secrets.compare_digest(credentials.credentials, _configured_key()):
        raise HTTPException(status_code=401, detail="Invalid API key")
