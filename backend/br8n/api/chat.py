"""POST /v1/chat — the funnel chat agent (br8n's OSS POC for delapan).

    message ─► select_preamble(maintained KB) ─► persona + <preamble> + funnel ─► stream

A deliberately minimal grounded chat loop — no LangGraph, no tools. Each message
embeds the question, taps the **maintained** agent KB through the existing preamble
path (`select_preamble`), assembles a persona + grounding + funnel system prompt, and
streams a completion. Stateless: short history rides in the request body, so the
server holds nothing between turns and scales horizontally.

The agent grounds **live** on whatever the backing store returns (Supabase on the
deploy, local SQLite for a forker) — so curating the KB updates the agent on the next
message, no redeploy. Gated by ``BR8N_CHAT`` (default on).
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from br8n.agent.preamble import Depth, select_preamble
from br8n.agent.state import Principal
from br8n.api.auth import require_principal
from br8n.clients.ai_gateway import stream_completion
from br8n.config import get_config
from br8n.interfaces.mcp.tenancy import resolve_tenant
from br8n.store import get_store

router = APIRouter(prefix="/v1", dependencies=[Depends(require_principal)])


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = Field(default_factory=list)


_SYSTEM_TEMPLATE = (
    "You are the br8n assistant — the front door to br8n, an open-source "
    "context-capture & resume engine, and its managed counterpart, delapan.\n\n"
    "VOICE: concise and technical, developer-to-developer. No hype, no emoji. "
    "Answer in 1–3 short paragraphs.\n\n"
    "GROUNDING: answer from the <preamble> context below. If it doesn't cover the "
    "question, say plainly what you do and don't know and offer to follow up — never "
    "invent specifics (pricing, features, benchmarks) that aren't in the context.\n\n"
    "FUNNEL: the br8n engine is free and MIT-licensed. The managed infrastructure — "
    "hosted knowledge bases, cross-machine sync, cross-repo search, team sharing — is "
    "delapan (paid). When the visitor's need maps to that managed infra, surface "
    "delapan and offer the next step; when they just want the free OSS tool, help with "
    "that and don't push.\n\n"
    "{preamble}\n"
)


def _agent_target() -> tuple[str, str]:
    """The (project, kb) the agent grounds on — env overrides the config defaults so a
    deploy can repoint without a code change."""
    cfg = get_config().chat
    return (
        os.getenv("BR8N_AGENT_PROJECT", cfg.agent_project),
        os.getenv("BR8N_AGENT_KB", cfg.agent_kb),
    )


def build_system_prompt(preamble_xml: str) -> str:
    """Persona + grounding + funnel. Split out so it's unit-testable without IO."""
    return _SYSTEM_TEMPLATE.format(preamble=preamble_xml)


@router.post("/chat")
async def chat(req: ChatRequest, principal: Principal = Depends(require_principal)) -> StreamingResponse:
    """Stream a grounded answer (SSE: ``data: {"delta": "..."}`` lines, then
    ``data: [DONE]``). 404 when ``BR8N_CHAT=0``; 503 when the agent KB is missing."""
    if os.getenv("BR8N_CHAT", "1") == "0":
        raise HTTPException(status_code=404, detail="chat is disabled")
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="message is empty")

    cfg = get_config().chat
    project, kb = _agent_target()
    try:
        ctx = resolve_tenant(project, kb, create=False, principal=principal)
    except Exception:  # noqa: BLE001 — unknown/unseeded agent KB: the agent has nothing to ground on
        raise HTTPException(status_code=503, detail=f"agent KB {project}/{kb} is not available")

    store = get_store(ctx.access_token, org_id=ctx.org_id)
    depth: Depth = cfg.preamble_depth if cfg.preamble_depth in ("shallow", "normal", "deep") else "normal"
    preamble_xml, _coverage = await select_preamble(req.message, store=store, kb_id=ctx.kb_id, depth=depth)

    messages: list[dict] = [{"role": "system", "content": build_system_prompt(preamble_xml)}]
    for turn in req.history[-cfg.history_turns:]:
        if turn.role in ("user", "assistant") and turn.content:
            messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": req.message})

    model = os.getenv("BR8N_CHAT_MODEL", cfg.model)

    async def sse() -> AsyncIterator[bytes]:
        try:
            async for delta in stream_completion(
                model=model,
                messages=messages,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                fallback_model=cfg.fallback_model,
            ):
                yield f"data: {json.dumps({'delta': delta})}\n\n".encode()
        except Exception as exc:  # noqa: BLE001 — surface the failure in-band, don't 500 mid-stream
            yield f"data: {json.dumps({'error': str(exc)})}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")
