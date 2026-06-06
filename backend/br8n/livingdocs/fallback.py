"""Backend fallback note distiller — synthesize a session note from snapshots.

A session note is normally written by the agent at session end (rich). When that
didn't happen (e.g. the capture came from the background watcher with no agent
summary), the backend distills a thinner note from the session's recent
snapshots. The result is persisted via ``persist_note(..., source="backend")``,
which stamps it as lower-confidence.

Two layers:

* ``synth_note_markdown`` — PURE, deterministic snapshots → markdown. No LLM.
* ``distill_fallback_note`` — best-effort async path: pull the recent snapshots,
  build the deterministic note, optionally polish it with a gated LLM, and
  persist. Mirrors the activity-KG gated-LLM pattern. Never raises.
"""

from __future__ import annotations

import logging
import os
import re

from pydantic import BaseModel, Field

from br8n.agent.state import TenantContext
from br8n.clients.ai_gateway import structured_completion
from br8n.config import get_config
from br8n.livingdocs.notes import persist_note
from br8n.livingdocs.paths import DocPaths
from br8n.livingdocs.policy import load_policy
from br8n.store import get_store

logger = logging.getLogger(__name__)

_FALLBACK_PLACEHOLDER = "_(no data — backend-distilled from snapshots)_"


def _is_changes_section(name: str) -> bool:
    """A "Changes"-like section gets the snapshot rollup; others get a placeholder."""
    return "change" in name.lower()


def _snapshot_bullet(snap: dict) -> str:
    """One bullet for a snapshot: its title plus any branch/cursor pulled from content."""
    title = (snap.get("title") or "").strip() or "(untitled snapshot)"
    content = snap.get("content") or ""
    extras: list[str] = []
    m = re.search(r"\*\*Branch\*\*:\s*`?([^`\n]+)`?", content)
    if m:
        extras.append(f"branch `{m.group(1).strip()}`")
    m = re.search(r"\*\*Cursor\*\*:\s*`?([^`\n]+)`?", content)
    if m:
        extras.append(f"cursor `{m.group(1).strip()}`")
    suffix = f" ({'; '.join(extras)})" if extras else ""
    return f"- {title}{suffix}"


def synth_note_markdown(snaps: list[dict], *, policy_sections: list[str]) -> str:
    """Deterministically synthesize a session note from snapshots.

    ``snaps`` is most-recent-first. The title comes from the most-recent
    snapshot's ``title``; each policy section gets either a snapshot rollup (for a
    "Changes"-like section) or a placeholder line. Always returns a valid titled
    markdown doc, even when ``snaps`` is empty. NO LLM — pure and deterministic.
    """
    title = ""
    if snaps:
        title = (snaps[0].get("title") or "").strip()
    title = title or "Session notes"

    lines: list[str] = [f"# {title}", ""]
    for name in policy_sections:
        lines.append(f"## {name}")
        if _is_changes_section(name) and snaps:
            lines.extend(_snapshot_bullet(s) for s in snaps)
        else:
            lines.append(_FALLBACK_PLACEHOLDER)
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


# --- gated LLM upgrade -------------------------------------------------------


class _PolishedNote(BaseModel):
    markdown: str = Field(default="", description="The improved note as markdown")


_POLISH_SYSTEM = (
    "You are improving a backend-distilled developer session note. You are given a "
    "deterministic draft (synthesized from workspace snapshots) and the section "
    "template it must follow. Rewrite it into a concise, useful note that keeps the "
    "exact same H1 title and the same '## <section>' headings in the same order. "
    "Fill each section from the snapshot evidence in the draft; if a section has no "
    "evidence, keep a short honest placeholder. Do not invent facts. "
    'Return JSON {"markdown": "..."}.'
)


async def _polish_markdown(draft: str, sections: list[str]) -> str:
    """Best-effort LLM polish of the deterministic draft. Returns the draft
    unchanged when the pass is disabled (``BR8N_LIVING_DOCS_LLM=0``) or fails."""
    if os.getenv("BR8N_LIVING_DOCS_LLM", "1") == "0":
        return draft
    cfg = get_config().living_docs
    user = (
        f"Section template (in order): {', '.join(sections)}\n\n"
        f"Deterministic draft:\n\n{draft}"
    )
    try:
        result = await structured_completion(
            model=cfg.distill_model,
            response_format=_PolishedNote,
            system=_POLISH_SYSTEM,
            user=user,
            temperature=cfg.temperature,
            fallback_model=cfg.distill_fallback_model,
            use_json_schema=False,
        )
        polished = (result.markdown or "").strip()
    except Exception as exc:  # noqa: BLE001 — polish is best-effort
        logger.warning("fallback note polish failed (%s); using deterministic draft", exc)
        return draft
    if not polished.lstrip().startswith("#"):
        # Don't trust a malformed result; fall back to the deterministic draft.
        return draft
    return polished + "\n" if not polished.endswith("\n") else polished


# --- persistence path (best-effort) ------------------------------------------


async def distill_fallback_note(
    ctx: TenantContext,
    *,
    project_path: str,
    kb: str,
    session_id: str,
    max_snaps: int = 8,
) -> dict | None:
    """Distill a backend note from the KB's recent snapshots and persist it.

    Returns ``persist_note``'s ``{"finding_id", "note_path"}`` on success, or
    ``None`` when there's nothing to distill or anything goes wrong (best-effort:
    never raises). Snapshots can't be filtered by session id (watcher captures
    carry no session in provenance), so "the session" is the most-recent
    ``max_snaps`` snapshots.
    """
    try:
        store = get_store(ctx.access_token, org_id=ctx.org_id)

        listed = store.list_findings(ctx.kb_id, category="snapshot", limit=max_snaps)
        if listed.get("count", 0) == 0:
            return None

        # The list view omits content; fetch each full record (best-effort per item).
        snaps: list[dict] = []
        for row in listed.get("findings", []):
            fid = row.get("id")
            if not fid:
                continue
            try:
                full = store.get_finding(ctx.kb_id, fid)
            except Exception as exc:  # noqa: BLE001 — skip a single bad fetch
                logger.warning("fallback distill: get_finding(%s) failed (%s); skipping", fid, exc)
                continue
            snaps.append({"title": full.get("title") or "", "content": full.get("content") or ""})

        if not snaps:
            return None

        sections = [s.name for s in load_policy(DocPaths(project_path, kb)).sections if s.enabled]
        content = synth_note_markdown(snaps, policy_sections=sections)
        content = await _polish_markdown(content, sections)

        title = (snaps[0].get("title") or "").strip() or "Session notes"
        return await persist_note(
            ctx,
            project_path=project_path,
            kb=kb,
            content=content,
            session_id=session_id,
            title=title,
            source="backend",
        )
    except Exception:  # noqa: BLE001 — best-effort: never break the caller
        logger.exception("fallback note distillation failed (kb=%s, session=%s)", kb, session_id)
        return None
