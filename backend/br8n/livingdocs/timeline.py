"""The append-only activity timeline — notes/captures/journal → ``.br8n/timeline/``.

    note/capture/journal ─► run_timeline ─┬─ append all-time.md (cursor-bounded)
                                          └─ regenerate recent.md / week.md (windowed)
                ▲
   schedule_timeline (debounced, fire-and-forget) ◄── persist_note / persist_snapshot

The all-time log is **append-only** — never rewritten; a ``## YYYY-MM-DD`` divider is
emitted when the day rolls over. The two window files are regenerated each pass from a
fresh windowed read, with optional LLM one-line day-headers (gated). Mirrors
``distill.py``/``activity.py``: module-level ``_BG_TASKS``, env gates, best-effort.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from br8n.agent.state import TenantContext
from br8n.clients.ai_gateway import structured_completion
from br8n.config import get_config
from br8n.constants import JOURNAL_SCOPE
from br8n.interfaces.mcp.tenancy import resolve_tenant
from br8n.livingdocs.paths import DocPaths, ensure_layout
from br8n.livingdocs.state import (
    load_timeline_state,
    save_timeline_state,
    should_roll,
)
from br8n.store import get_store

logger = logging.getLogger(__name__)


# --- event carrier -----------------------------------------------------------

@dataclass
class TimelineEvent:
    ts: str     # ISO-8601 created_at
    kind: str   # "note" | "capture" | "journal"
    title: str
    gist: str   # one-line
    id: str


def _event_day(e: TimelineEvent) -> str:
    """YYYY-MM-DD of the event timestamp (UTC, tolerant of 'Z'/naive)."""
    try:
        dt = datetime.fromisoformat(e.ts.replace("Z", "+00:00"))
    except Exception:
        return (e.ts or "")[:10]
    return dt.date().isoformat()


def _event_time(e: TimelineEvent) -> str:
    """HH:MM of the event timestamp; '' if unparseable."""
    try:
        dt = datetime.fromisoformat(e.ts.replace("Z", "+00:00"))
    except Exception:
        return ""
    return dt.strftime("%H:%M")


def _event_line(e: TimelineEvent) -> str:
    """`HH:MM · <kind> · <title> — <gist>` (gist omitted if empty)."""
    gist = (e.gist or "").strip().replace("\n", " ")
    head = f"{_event_time(e)} · {e.kind} · {e.title.strip()}"
    return f"{head} — {gist}" if gist else head


def _sort_key(e: TimelineEvent) -> tuple[str, str]:
    return (e.ts, e.id)


# --- all-time append (pure file I/O, deterministic) --------------------------

def append_all_time(
    paths: DocPaths,
    project: str,
    kb: str,
    events: list[TimelineEvent],
    *,
    last_appended_day: str,
) -> str:
    """Append `events` (already sorted ascending) to all-time.md; never rewrite.

    Writes the `# Activity — <project>/<kb>` H1 once on first creation. Emits a
    `## YYYY-MM-DD` divider whenever the event's day differs from the running
    `last_appended_day`. Returns the new `last_appended_day`.
    """
    ensure_layout(paths)
    paths.timeline_dir.mkdir(parents=True, exist_ok=True)
    f = paths.timeline_dir / "all-time.md"
    chunks: list[str] = []
    if not f.exists():
        chunks.append(f"# Activity — {project}/{kb}\n")
    day = last_appended_day
    for e in events:
        d = _event_day(e)
        if d != day:
            chunks.append(f"\n## {d}\n")
            day = d
        chunks.append(_event_line(e) + "\n")
    if chunks:
        with f.open("a", encoding="utf-8") as fh:
            fh.write("".join(chunks))
    return day


# --- window render (pure; LLM headers passed in) -----------------------------

def render_window(
    name: str,
    events: list[TimelineEvent],
    *,
    day_headers: dict[str, str] | None,
) -> str:
    """Render a window view (recent/week) grouped by day, ascending.

    `day_headers` maps `YYYY-MM-DD` → a one-line summary; when None (LLM off) or a
    day is missing, a plain `## YYYY-MM-DD` divider is used.
    """
    lines: list[str] = [f"# Activity · {name}\n"]
    cur = ""
    for e in events:
        d = _event_day(e)
        if d != cur:
            summary = (day_headers or {}).get(d, "").strip()
            header = f"## {d} — {summary}" if summary else f"## {d}"
            lines.append(f"\n{header}\n")
            cur = d
        lines.append(_event_line(e) + "\n")
    return "".join(lines)
