"""Persisted Living Docs distill state + the debounce decision.

Mirrors the load/save convention used elsewhere: default on a missing or corrupt
file, never raise. The state tracks how many notes have accumulated since the last
distill and when that distill ran, so `should_distill` can debounce re-distillation
on either an N-notes or a T-minutes threshold.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel

from br8n.livingdocs.paths import DocPaths, ensure_layout


class DocsState(BaseModel):
    # folder name → list of note-file basenames / topic keys it contains
    taxonomy: dict[str, list[str]] = {}
    # notes appended since the last distill run
    notes_since_distill: int = 0
    # ISO-8601 UTC timestamp of the last distill; "" means never
    last_distill_at: str = ""


def load_state(paths: DocPaths) -> DocsState:
    """Read the on-disk state; return a default `DocsState` on any failure."""
    try:
        raw = paths.state_path.read_text()
    except (FileNotFoundError, OSError):
        return DocsState()
    try:
        return DocsState.model_validate_json(raw)
    except Exception:
        # Corrupt JSON or schema drift — fall back to default, never crash.
        return DocsState()


def save_state(paths: DocPaths, state: DocsState) -> None:
    """Persist the state to disk, creating the layout if needed."""
    ensure_layout(paths)
    paths.state_path.write_text(json.dumps(state.model_dump(), indent=2) + "\n")


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp, tolerating a trailing 'Z' and naive values."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class TimelineState(BaseModel):
    # cursor: the most recently APPENDED event (advances all-time.md)
    last_event_ts: str = ""      # ISO-8601 UTC of the last appended event
    last_event_id: str = ""      # its finding id (tie-break on equal ts)
    last_appended_day: str = ""  # YYYY-MM-DD of the last line in all-time.md
    # debounce
    events_since_pass: int = 0   # events appended-or-pending since the last pass
    last_pass_at: str = ""       # ISO-8601 UTC of the last completed pass; "" = never


def load_timeline_state(paths: DocPaths) -> TimelineState:
    """Read on-disk timeline state; default `TimelineState` on any failure."""
    try:
        raw = paths.timeline_state_path.read_text()
    except (FileNotFoundError, OSError):
        return TimelineState()
    try:
        return TimelineState.model_validate_json(raw)
    except Exception:  # corrupt JSON / schema drift — never crash
        return TimelineState()


def save_timeline_state(paths: DocPaths, state: TimelineState) -> None:
    """Persist timeline state, creating the layout if needed."""
    ensure_layout(paths)
    paths.timeline_state_path.write_text(json.dumps(state.model_dump(), indent=2) + "\n")


def should_roll(
    state: TimelineState,
    *,
    debounce_n: int,
    debounce_minutes: int,
    now_iso: str | None = None,
) -> bool:
    """Whether to run a timeline pass now (mirrors `should_distill`).

    - `< 1` pending → never.
    - `>= debounce_n` pending → now.
    - else if a prior pass exists → once `debounce_minutes` elapsed since it.
    - never-rolled and below the count threshold → wait.
    """
    if state.events_since_pass < 1:
        return False
    if state.events_since_pass >= debounce_n:
        return True
    if not state.last_pass_at:
        return False
    try:
        last = _parse_iso(state.last_pass_at)
        now = _parse_iso(now_iso) if now_iso else datetime.now(timezone.utc)
    except Exception:
        return False
    return (now - last).total_seconds() / 60.0 >= debounce_minutes


def should_distill(
    state: DocsState,
    *,
    debounce_n: int,
    debounce_minutes: int,
    now_iso: str | None = None,
) -> bool:
    """Decide whether to re-distill given the debounce thresholds.

    - Nothing pending (< 1 note) → never distill.
    - >= `debounce_n` pending notes → distill now (count threshold).
    - Otherwise, if a prior distill exists, distill once `debounce_minutes` have
      elapsed since it (time threshold).
    - Never distilled yet and below the count threshold → wait.
    """
    if state.notes_since_distill < 1:
        return False
    if state.notes_since_distill >= debounce_n:
        return True
    if not state.last_distill_at:
        # Never distilled and below the count threshold — wait for either threshold.
        return False
    try:
        last = _parse_iso(state.last_distill_at)
        now = _parse_iso(now_iso) if now_iso else datetime.now(timezone.utc)
    except Exception:
        # Unparseable timestamps — be conservative and don't trigger on time alone.
        return False
    elapsed_minutes = (now - last).total_seconds() / 60.0
    return elapsed_minutes >= debounce_minutes
