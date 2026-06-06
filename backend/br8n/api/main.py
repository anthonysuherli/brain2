"""br8n FastAPI application entry point.

Free (local) tier — the blessed launcher enforces loopback binding because the
local tier disables API auth (see ``br8n.api.auth``)::

    python -m br8n.api.main

It binds 127.0.0.1:8002 by default; override with ``BR8N_HOST`` / ``BR8N_PORT``.
On the local tier ``run()`` refuses any non-loopback host, so the unauthenticated
API can never be exposed on a public interface.

Cloud (paid) tier — auth is enforced by ``BR8N_API_KEY``, so raw uvicorn is fine::

    uvicorn br8n.api.main:app --reload --port 8002
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from br8n.api import activity, apple_auth, capture, chat, explore, health, projects, resume
from br8n.config import get_settings
from br8n.store import active_backend

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


_warned_local = False


def create_app() -> FastAPI:
    global _warned_local
    settings = get_settings()
    if active_backend() == "local" and not _warned_local:
        _warned_local = True
        logger.warning(
            "local tier: API auth is DISABLED; ensure loopback binding."
        )
    app = FastAPI(
        title="br8n",
        version="0.1.0",
        description="Context-capture and resume engine.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(capture.router)
    app.include_router(resume.router)
    app.include_router(projects.router)
    app.include_router(explore.router)
    app.include_router(activity.router)
    app.include_router(apple_auth.router)
    app.include_router(chat.router)
    return app


app = create_app()


def run() -> None:
    """Blessed local-run entrypoint: owns the bind host and refuses to expose the
    auth-less local tier on a non-loopback interface."""
    import os

    import uvicorn

    host = os.getenv("BR8N_HOST", "127.0.0.1")
    port = int(os.getenv("BR8N_PORT", "8002"))
    if active_backend() == "local" and host not in _LOOPBACK_HOSTS:
        raise SystemExit(
            f"Refusing to start: BR8N_BACKEND=local disables API auth, but host={host} "
            f"is not loopback. Bind to 127.0.0.1, or use the cloud backend with BR8N_API_KEY."
        )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
