"""brain2 FastAPI application entry point.

Cloud (paid) tier::

    uvicorn brain2.api.main:app --reload --port 8002

Free (local) tier — bind to loopback; no API key required (see brain2.api.auth)::

    BRAIN2_BACKEND=local uvicorn brain2.api.main:app --host 127.0.0.1 --port 8002

The local-tier auth bypass is safe ONLY because the server stays on 127.0.0.1.
Do not pass ``--host 0.0.0.0`` on the local tier.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from brain2.api import capture, explore, health, resume
from brain2.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="brain2",
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
    app.include_router(explore.router)
    return app


app = create_app()
