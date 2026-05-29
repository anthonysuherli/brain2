"""Persist a WorkspaceSnapshot as a Finding in the KB."""

from __future__ import annotations

from brain2.agent.state import TenantContext
from brain2.agent.synopsis import schedule_rebuild
from brain2.clients.embeddings import embed_batch
from brain2.clients.supabase import user_client

from brain2.capture.adapter import snapshot_to_finding
from brain2.capture.models import WorkspaceSnapshot


async def persist_snapshot(ctx: TenantContext, snap: WorkspaceSnapshot) -> str:
    """Embed + insert snapshot as a Finding. Returns the new finding id.

    Fires a synopsis rebuild after write (fire-and-forget in the caller)
    so the resume card stays current without blocking the capture response.
    """
    payload = snapshot_to_finding(snap)
    [embedding] = await embed_batch([payload["content"]])
    row = {
        "org_id": ctx.org_id,
        "kb_id": ctx.kb_id,
        "title": payload["title"],
        "content": payload["content"],
        "category": payload["category"],
        "confidence": 1.0,
        "tags": payload["tags"],
        "provenance": payload["provenance"],
        "embedding": embedding,
    }
    inserted = user_client(ctx.access_token).table("findings").insert(row).execute()
    finding_id: str = inserted.data[0]["id"]
    schedule_rebuild(ctx)
    return finding_id
