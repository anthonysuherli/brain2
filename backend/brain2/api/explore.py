"""Explore endpoints — gap-fill pipeline for Phase 3.

POST /v1/explore/{project}/{kb}  — start exploration, return exploration_id
GET  /v1/explore/{id}/status     — poll status + findings
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from brain2.agent.synopsis import schedule_rebuild
from brain2.api.auth import require_api_key
from brain2.clients.embeddings import embed_batch
from brain2.clients.supabase import service_client
from brain2.config import get_config
from brain2.exploration import run_exploration
from brain2.interfaces.mcp.tenancy import resolve_tenant

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
logger = logging.getLogger(__name__)


class ExploreRequest(BaseModel):
    prompt: str
    max_findings: int | None = None


class ExploreStarted(BaseModel):
    exploration_id: str
    status: str = "pending"
    project: str
    kb: str


class ExploreStatus(BaseModel):
    exploration_id: str
    status: str
    finding_count: int
    finding_ids: list[str]
    completed_at: str | None
    error: str | None


@router.post("/explore/{project}/{kb}", status_code=202, response_model=ExploreStarted)
async def start_explore(
    project: str,
    kb: str,
    body: ExploreRequest,
    background_tasks: BackgroundTasks,
) -> ExploreStarted:
    """Start the research pipeline for `prompt` and return an exploration_id.

    The pipeline runs in the background (plan→search→crawl→extract→merge).
    Poll GET /v1/explore/{id}/status for progress and results. When the
    coverage band on a resume card is `gap`, this is the action to take.
    """
    ctx = resolve_tenant(project, kb, create=True)
    sb = service_client()
    cfg = get_config().exploration
    max_findings = min(body.max_findings or cfg.default_max_findings, cfg.max_findings)

    row = (
        sb.table("explorations")
        .insert({
            "org_id": ctx.org_id,
            "kb_id": ctx.kb_id,
            "prompt": body.prompt,
            "status": "pending",
            "started_at": _now_iso(),
        })
        .execute()
    )
    exploration_id: str = row.data[0]["id"]

    background_tasks.add_task(
        _run_pipeline,
        exploration_id=exploration_id,
        prompt=body.prompt,
        ctx=ctx,
        max_findings=max_findings,
    )

    return ExploreStarted(
        exploration_id=exploration_id, status="pending", project=project, kb=kb
    )


@router.get("/explore/{exploration_id}/status", response_model=ExploreStatus)
async def explore_status(exploration_id: str) -> ExploreStatus:
    """Poll exploration progress. Status values: pending → planning → searching →
    crawling → extracting → merging → completed | failed."""
    sb = service_client()
    rows = (
        sb.table("explorations")
        .select("id, status, finding_ids, completed_at, error")
        .eq("id", exploration_id)
        .limit(1)
        .execute()
    ).data
    if not rows:
        raise HTTPException(status_code=404, detail="exploration not found")
    row = rows[0]
    finding_ids: list[str] = row.get("finding_ids") or []
    return ExploreStatus(
        exploration_id=exploration_id,
        status=row.get("status", "unknown"),
        finding_count=len(finding_ids),
        finding_ids=finding_ids,
        completed_at=row.get("completed_at"),
        error=row.get("error"),
    )


# ---------------------------------------------------------------------------
# Background pipeline
# ---------------------------------------------------------------------------

async def _run_pipeline(
    *,
    exploration_id: str,
    prompt: str,
    ctx,
    max_findings: int,
) -> None:
    """Run the exploration pipeline, persist findings, update the row."""
    sb = service_client()
    cfg = get_config().exploration

    async def on_progress(phase: str) -> None:
        _durable_phases = frozenset({"planning", "searching", "crawling", "extracting", "merging"})
        if phase in _durable_phases:
            try:
                sb.table("explorations").update({"status": phase}).eq("id", exploration_id).execute()
            except Exception:
                pass

    try:
        findings = await run_exploration(
            prompt,
            exploration_id=exploration_id,
            project_id=ctx.project_id,
            kb_id=ctx.kb_id,
            cfg=cfg,
            on_progress=on_progress,
        )
        captured = findings[:max_findings]
        finding_ids = await _persist_findings(ctx, captured, exploration_id)
        sb.table("explorations").update({
            "status": "completed",
            "completed_at": _now_iso(),
            "finding_ids": finding_ids,
        }).eq("id", exploration_id).execute()
        schedule_rebuild(ctx)
    except Exception as exc:
        logger.exception("exploration %s failed", exploration_id)
        try:
            sb.table("explorations").update({
                "status": "failed",
                "completed_at": _now_iso(),
                "error": str(exc),
            }).eq("id", exploration_id).execute()
        except Exception:
            pass


async def _persist_findings(ctx, findings: list, exploration_id: str) -> list[str]:
    if not findings:
        return []
    rows: list[dict] = []
    contents: list[str] = []
    for f in findings:
        body = _render_content(f.content)
        rows.append({
            "org_id": ctx.org_id,
            "kb_id": ctx.kb_id,
            "title": f.title,
            "content": body,
            "category": f.category,
            "confidence": float(f.confidence) if f.confidence is not None else None,
            "tags": list(f.tags or []),
            "provenance": _normalize_provenance(f.provenance),
        })
        contents.append(body)
    embeddings = await embed_batch(contents)
    for row, emb in zip(rows, embeddings):
        row["embedding"] = emb
    inserted = service_client().table("findings").insert(rows).execute()
    return [r["id"] for r in inserted.data or []]


def _render_content(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return str(content)
    if not content:
        return ""
    if len(content) == 1:
        only = next(iter(content.values()))
        if isinstance(only, str):
            return only
    lines: list[str] = []
    for key, value in content.items():
        label = key.replace("_", " ").title()
        if isinstance(value, (list, dict)):
            lines.append(f"**{label}**:\n```json\n{json.dumps(value, indent=2)}\n```")
        else:
            lines.append(f"**{label}**: {value}")
    return "\n".join(lines)


def _normalize_provenance(provenance) -> list[dict]:
    if not provenance:
        return []
    out: list[dict] = []
    for p in provenance:
        if isinstance(p, dict):
            entry = dict(p)
            entry.setdefault("accessed_at", _now_iso())
            out.append(entry)
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
