"""GET /v1/projects — discovery for native clients.

The editor already knows its project + branch; a phone does not. This lists the
caller's repos (projects) and branches (KBs) with the chips the home screen
shows — last activity + snapshot count — so the app can route into a resume card
without the user typing anything. Read-only; backed by the active `Store`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from brain2.api.auth import require_api_key
from brain2.store import get_store

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


class KBSummary(BaseModel):
    kb: str
    kb_id: str
    last_activity: str | None = None
    snapshot_count: int


class ProjectSummary(BaseModel):
    project: str
    project_id: str
    kbs: list[KBSummary] = []


class ProjectsResponse(BaseModel):
    projects: list[ProjectSummary]


@router.get("/projects", response_model=ProjectsResponse)
async def list_projects() -> ProjectsResponse:
    """List the caller's projects + KBs (cloud scopes to the authenticated org)."""
    store = get_store()
    return ProjectsResponse(projects=store.list_projects())
