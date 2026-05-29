"""KB synopsis spine: the always-on preamble's stable layer.

    findings (titles+categories) ─► fast LLM ─► [{topic, gloss}] ─► kb_synopsis

Regen is incremental + fire-and-forget: `maybe_rebuild_synopsis` is awaited as a
detached task after each persist, so chat turns never block on it. Storage is the
`kb_synopsis` table (one current row per KB, upserted on kb_id).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import cast

from supabase import Client

from brain2.agent.state import TenantContext
from brain2.clients.anthropic import chat_model
from brain2.clients.supabase import service_client
from brain2.config import SynopsisConfig, get_config

logger = logging.getLogger(__name__)


def should_rebuild(live_count: int, row: dict | None, cfg: SynopsisConfig) -> bool:
    if live_count <= 0:
        return False
    if row is None:
        return True
    if live_count - int(row.get("finding_count_at_build", 0)) >= cfg.rebuild_delta:
        return True
    built_at = row.get("built_at")
    if built_at:
        ts = datetime.fromisoformat(str(built_at).replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        if age_h >= cfg.rebuild_max_age_hours:
            return True
    return False


def _build_prompt(findings: list[dict], cfg: SynopsisConfig) -> str:
    lines = [f"- {f.get('title', '')} [{f.get('category', '')}]" for f in findings]
    catalogue = "\n".join(lines)
    return (
        "You are summarizing a knowledge base into a compact orientation spine.\n"
        f"Below are its findings (title [category]).\n\n{catalogue}\n\n"
        f"Produce at most {cfg.max_entries} entries naming the KB's main topics. "
        "Return ONLY JSON: a list of objects with keys `topic` (short noun phrase) "
        "and `gloss` (one sentence on what the KB knows about it)."
    )


def load_synopsis(client: Client, kb_id: str) -> dict | None:
    res = (
        client.table("kb_synopsis")
        .select("content, finding_count_at_build, built_at, model")
        .eq("kb_id", kb_id)
        .limit(1)
        .execute()
    )
    return cast("dict | None", (res.data or [None])[0])


async def _build(findings: list[dict], cfg: SynopsisConfig) -> list[dict]:
    llm = chat_model(cfg.model)
    resp = await llm.ainvoke([{"role": "user", "content": _build_prompt(findings, cfg)}])
    text = resp.content if isinstance(resp.content, str) else ""
    try:
        data = json.loads(text[text.find("[") : text.rfind("]") + 1])
        # Load-bearing: the dict-filter keeps the [:max_entries] slice safe — a
        # mis-sliced non-dict list (e.g. a parsed JSON object) degrades to [].
        return [e for e in data if isinstance(e, dict)][: cfg.max_entries]
    except (ValueError, json.JSONDecodeError):
        logger.warning("synopsis JSON parse failed; len=%d", len(text))
        return []


async def maybe_rebuild_synopsis(ctx: TenantContext) -> None:
    """Fire-and-forget: rebuild the synopsis if the KB grew enough. Never raises."""
    try:
        cfg = get_config().synopsis
        sb = service_client()
        count_res = (
            sb.table("findings")
            .select("id", count="exact")
            .eq("kb_id", ctx.kb_id)
            .limit(1)
            .execute()
        )
        live_count = count_res.count or 0
        row = load_synopsis(sb, ctx.kb_id)
        if not should_rebuild(live_count, row, cfg):
            return
        rows = (
            sb.table("findings")
            .select("title, category")
            .eq("kb_id", ctx.kb_id)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        ).data or []
        findings = [f for f in rows if isinstance(f, dict)]
        content = await _build(findings, cfg)
        sb.table("kb_synopsis").upsert(
            {
                "org_id": ctx.org_id,
                "kb_id": ctx.kb_id,
                "content": content,
                "finding_count_at_build": live_count,
                "model": cfg.model,
                "built_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="kb_id",
        ).execute()
    except Exception:  # noqa: BLE001 — regen is best-effort, never breaks a turn
        logger.exception("synopsis rebuild failed for kb=%s", ctx.kb_id)


_BG_TASKS: set[asyncio.Task] = set()


def schedule_rebuild(ctx: TenantContext) -> None:
    """Fire-and-forget synopsis regen that won't be GC'd mid-flight.

    Holds a strong ref in a module-level set until the task finishes (CPython's
    event loop only weak-refs tasks, so an unreferenced create_task can vanish)."""
    task = asyncio.create_task(maybe_rebuild_synopsis(ctx))
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
