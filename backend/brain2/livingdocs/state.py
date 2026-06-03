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

from brain2.livingdocs.paths import DocPaths, ensure_layout


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
