# `/br8n:timeline` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-repo+branch, append-only **activity timeline** built from notes + captures + journal — one canonical `all-time.md` log plus regenerated `recent.md`/`week.md` window views — surfaced via a `br8n_timeline` MCP tool and a `/br8n:timeline` skill, populated by a debounced background pass.

**Architecture:** A new `br8n/livingdocs/timeline.py` mirrors `distill.py`/`activity.py` (module-level `_BG_TASKS`, env gates, best-effort). A cursor in `TimelineState` makes the background pass incremental: it appends only events newer than the cursor to `all-time.md` (never rewritten) and regenerates the two windowed views from a fresh windowed read. `schedule_timeline` is wired wherever notes/captures are created.

**Tech Stack:** Python 3.11, pydantic v2, pytest + pytest-asyncio (`asyncio_mode = "auto"`), the `Store` protocol (SQLite local tier in tests), FastMCP tool registration, the `structured_completion` AI-gateway client for the gated LLM day-headers.

**Spec:** `docs/plans/2026-06-07-timeline-design.md`

**Conventions for every task:** `from __future__ import annotations` at the top of new modules; ruff line-length 100; terse module docstring with an ASCII flow diagram on new modules; best-effort code never raises into a session. Run tests from `backend/` with the project venv (`cd backend && .venv/bin/pytest …` or `uv run pytest …`).

---

### Task 1: Config knobs

**Files:**
- Modify: `backend/br8n/config.py:172-187` (`LivingDocsConfig`)
- Test: `backend/tests/test_livingdocs_config.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_livingdocs_config.py`:

```python
def test_timeline_config_defaults():
    from br8n.config import LivingDocsConfig

    cfg = LivingDocsConfig()
    assert cfg.timeline_dirname == "timeline"
    assert cfg.timeline_state_filename == "timeline-state.json"
    assert cfg.timeline_debounce_n == 3
    assert cfg.timeline_debounce_minutes == 60
    assert cfg.recent_days == 3
    assert cfg.week_days == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_livingdocs_config.py::test_timeline_config_defaults -v`
Expected: FAIL — `AttributeError: 'LivingDocsConfig' object has no attribute 'timeline_dirname'`

- [ ] **Step 3: Add the fields**

In `backend/br8n/config.py`, inside `LivingDocsConfig`, immediately after the line
`cluster_min_notes: int = 5` (line 184), add:

```python
    # --- timeline (append-only activity log) ---
    timeline_dirname: str = "timeline"
    timeline_state_filename: str = "timeline-state.json"
    # Timeline rollup debounce: roll after N new events OR T minutes since last pass.
    timeline_debounce_n: int = 3
    timeline_debounce_minutes: int = 60
    recent_days: int = 3   # recent.md window
    week_days: int = 7     # week.md window
```

(The LLM day-headers reuse the existing `distill_model`, `distill_fallback_model`,
and `temperature` — do not add new model fields.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_livingdocs_config.py::test_timeline_config_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/br8n/config.py backend/tests/test_livingdocs_config.py
git commit -m "feat(timeline): add LivingDocsConfig timeline knobs"
```

---

### Task 2: Paths

**Files:**
- Modify: `backend/br8n/livingdocs/paths.py:34-43` (`DocPaths`)
- Test: `backend/tests/test_livingdocs_paths.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_livingdocs_paths.py`:

```python
def test_timeline_paths(tmp_path):
    from br8n.livingdocs.paths import DocPaths

    p = DocPaths(project_path=str(tmp_path), kb="main")
    assert p.timeline_dir == p.root / "timeline"
    assert p.timeline_state_path == p.root / "timeline-state.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_livingdocs_paths.py::test_timeline_paths -v`
Expected: FAIL — `AttributeError: 'DocPaths' object has no attribute 'timeline_dir'`

- [ ] **Step 3: Add the properties**

In `backend/br8n/livingdocs/paths.py`, inside `DocPaths`, after the `docs_dir`
property (ends line 35), add:

```python
    @property
    def timeline_dir(self) -> Path:
        return self.root / self._cfg.timeline_dirname

    @property
    def timeline_state_path(self) -> Path:
        return self.root / self._cfg.timeline_state_filename
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_livingdocs_paths.py::test_timeline_paths -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/br8n/livingdocs/paths.py backend/tests/test_livingdocs_paths.py
git commit -m "feat(timeline): add timeline_dir + timeline_state_path to DocPaths"
```

---

### Task 3: `TimelineState` + `should_roll`

**Files:**
- Modify: `backend/br8n/livingdocs/state.py` (add `TimelineState`, loaders, `should_roll`)
- Test: `backend/tests/test_timeline_state.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_timeline_state.py`:

```python
from br8n.livingdocs.paths import DocPaths
from br8n.livingdocs.state import (
    TimelineState,
    load_timeline_state,
    save_timeline_state,
    should_roll,
)


def test_timeline_state_roundtrip(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    st = load_timeline_state(p)
    assert st.events_since_pass == 0
    assert st.last_event_ts == ""
    st.events_since_pass = 2
    st.last_event_ts = "2026-06-07T10:00:00+00:00"
    st.last_event_id = "abc"
    st.last_appended_day = "2026-06-07"
    save_timeline_state(p, st)
    reloaded = load_timeline_state(p)
    assert reloaded.events_since_pass == 2
    assert reloaded.last_event_id == "abc"
    assert reloaded.last_appended_day == "2026-06-07"


def test_load_returns_default_when_absent(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    st = load_timeline_state(p)
    assert st.events_since_pass == 0
    assert st.last_pass_at == ""


def test_corrupt_timeline_state_falls_back(tmp_path):
    from br8n.livingdocs.paths import ensure_layout

    p = DocPaths(project_path=str(tmp_path), kb="main")
    ensure_layout(p)
    p.timeline_state_path.write_text("{ not valid json")
    st = load_timeline_state(p)  # must not raise
    assert st.events_since_pass == 0


def test_should_roll_count_threshold():
    st = TimelineState(events_since_pass=3)
    assert should_roll(st, debounce_n=3, debounce_minutes=60) is True


def test_should_roll_nothing_pending():
    st = TimelineState(events_since_pass=0, last_pass_at="2000-01-01T00:00:00+00:00")
    assert should_roll(st, debounce_n=3, debounce_minutes=60) is False


def test_should_roll_time_threshold():
    st = TimelineState(events_since_pass=1, last_pass_at="2026-01-01T00:00:00+00:00")
    assert should_roll(
        st, debounce_n=3, debounce_minutes=60, now_iso="2026-01-01T01:30:00+00:00"
    ) is True
    assert should_roll(
        st, debounce_n=3, debounce_minutes=60, now_iso="2026-01-01T00:30:00+00:00"
    ) is False


def test_should_roll_never_rolled_below_count_waits():
    st = TimelineState(events_since_pass=1, last_pass_at="")
    assert should_roll(st, debounce_n=3, debounce_minutes=60) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_state.py -v`
Expected: FAIL — `ImportError: cannot import name 'TimelineState'`

- [ ] **Step 3: Implement `TimelineState` + loaders + `should_roll`**

In `backend/br8n/livingdocs/state.py`, the helper `_parse_iso` already exists (reuse
it). Add at the end of the file:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_state.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/br8n/livingdocs/state.py backend/tests/test_timeline_state.py
git commit -m "feat(timeline): TimelineState cursor + should_roll debounce"
```

---

### Task 4: `timeline.py` — event carrier + deterministic rendering

**Files:**
- Create: `backend/br8n/livingdocs/timeline.py`
- Test: `backend/tests/test_timeline_render.py` (new)

This task creates the module with the pure, deterministic pieces only:
the `TimelineEvent` carrier, line/day helpers, the all-time append helper, and the
deterministic (LLM-off) window renderer. Store access + orchestration come in later
tasks.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_timeline_render.py`:

```python
from br8n.livingdocs.timeline import (
    TimelineEvent,
    _event_day,
    _event_line,
    append_all_time,
    render_window,
)
from br8n.livingdocs.paths import DocPaths


def _ev(ts, kind, title, gist, _id):
    return TimelineEvent(ts=ts, kind=kind, title=title, gist=gist, id=_id)


def test_event_line_and_day():
    e = _ev("2026-06-07T14:30:00+00:00", "note", "Storage choice", "Chose SQLite", "f1")
    assert _event_day(e) == "2026-06-07"
    line = _event_line(e)
    assert "14:30" in line
    assert "note" in line
    assert "Storage choice" in line
    assert "Chose SQLite" in line


def test_append_all_time_writes_header_and_day_divider_once(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    events = [
        _ev("2026-06-07T09:00:00+00:00", "note", "A", "ga", "1"),
        _ev("2026-06-07T11:00:00+00:00", "capture", "B", "gb", "2"),
        _ev("2026-06-08T08:00:00+00:00", "journal", "C", "gc", "3"),
    ]
    last_day = append_all_time(p, "br8n", "main", events, last_appended_day="")
    text = p.timeline_dir.joinpath("all-time.md").read_text()
    assert text.startswith("# Activity — br8n/main")
    assert text.count("## 2026-06-07") == 1  # single divider for the day
    assert text.count("## 2026-06-08") == 1
    assert last_day == "2026-06-08"
    # newest at the bottom (ascending): C's line comes after A's line
    assert text.index("\nA — ".replace("A — ", "")) >= 0  # smoke
    assert text.index(" · A —") < text.index(" · C —")


def test_append_all_time_is_additive_not_rewritten(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    first = [_ev("2026-06-07T09:00:00+00:00", "note", "First", "g1", "1")]
    day = append_all_time(p, "br8n", "main", first, last_appended_day="")
    second = [_ev("2026-06-07T10:00:00+00:00", "note", "Second", "g2", "2")]
    append_all_time(p, "br8n", "main", second, last_appended_day=day)
    text = p.timeline_dir.joinpath("all-time.md").read_text()
    assert "First" in text and "Second" in text   # first pass preserved
    assert text.count("# Activity — br8n/main") == 1  # header written once
    assert text.count("## 2026-06-07") == 1           # divider not duplicated


def test_render_window_groups_by_day_plain_headers(tmp_path):
    events = [
        _ev("2026-06-07T09:00:00+00:00", "note", "A", "ga", "1"),
        _ev("2026-06-08T08:00:00+00:00", "note", "B", "gb", "2"),
    ]
    out = render_window("recent", events, day_headers=None)  # None → plain dividers
    assert "## 2026-06-07" in out and "## 2026-06-08" in out
    assert out.index("## 2026-06-07") < out.index("## 2026-06-08")  # ascending


def test_render_window_uses_llm_day_headers_when_given(tmp_path):
    events = [_ev("2026-06-07T09:00:00+00:00", "note", "A", "ga", "1")]
    out = render_window("recent", events, day_headers={"2026-06-07": "Set up storage"})
    assert "## 2026-06-07 — Set up storage" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'br8n.livingdocs.timeline'`

- [ ] **Step 3: Create the module with the pure pieces**

Create `backend/br8n/livingdocs/timeline.py`:

```python
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
```

(The store-touching functions `_gather_events`, `_infer_day_headers`, `run_timeline`,
and `schedule_timeline` are added in Tasks 5–7. The imports above for
`structured_completion`, `resolve_tenant`, `get_store`, `should_roll`, etc. are used by
those later tasks — they are intentionally present now so the module is import-stable.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_render.py -v`
Expected: PASS (5 passed). (Unused-import warnings are fine; later tasks consume them.)

- [ ] **Step 5: Commit**

```bash
git add backend/br8n/livingdocs/timeline.py backend/tests/test_timeline_render.py
git commit -m "feat(timeline): TimelineEvent + deterministic all-time/window rendering"
```

---

### Task 5: Event gathering from the three sources

**Files:**
- Modify: `backend/br8n/livingdocs/timeline.py` (add `_gather_events`)
- Test: `backend/tests/test_timeline_gather.py` (new)

`_gather_events` reads notes (`category="note"`) + captures (`category="snapshot"`)
from the KB, and journal (`category="journal"`) from the `JOURNAL_SCOPE` KB filtered to
`provenance.project == project`. Each source is best-effort (a raising source is
skipped). `since` is the cursor `(ts, id)` tuple, or None for "all".

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_timeline_gather.py`:

```python
import hashlib

import pytest

DIM = 1536


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


@pytest.mark.asyncio
async def test_gather_events_collects_notes_captures_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))

    import br8n.store as store_pkg
    import br8n.livingdocs.notes as notes_mod
    import br8n.livingdocs.journal as journal_mod

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)
    monkeypatch.setattr(journal_mod, "embed_batch", _fake_embed_batch)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.livingdocs.journal import persist_journal
    from br8n.livingdocs.timeline import _gather_events
    from br8n.capture.models import WorkspaceSnapshot
    from br8n.capture.service import persist_snapshot

    ctx = resolve_tenant("proj", "main", create=True)
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# Note one\n\nDecided on the cursor design.",
        session_id="s1", title="Note one",
    )
    snap = WorkspaceSnapshot(
        project_path=str(tmp_path), trigger="manual",
        captured_at="2026-06-07T12:00:00+00:00", branch="main",
        git_diff_stat="1 file changed", open_files=[],
        hypothesis="Wiring the timeline",
    )
    await persist_snapshot(ctx, snap)

    jctx = resolve_tenant("__journal__", "__journal__", create=True)
    await persist_journal(
        jctx, text="A thought about timelines.", type="insight",
        originating_project="proj",
    )
    await persist_journal(
        jctx, text="Unrelated project note.", type="insight",
        originating_project="other-proj",
    )

    events = await _gather_events(ctx, project="proj", since=None)
    kinds = sorted({e.kind for e in events})
    assert kinds == ["capture", "journal", "note"]
    titles = [e.title for e in events]
    assert "Note one" in titles
    # journal filtered to this project only
    journal_titles = [e.title for e in events if e.kind == "journal"]
    assert any("thought about timelines" in t.lower() for t in journal_titles)
    assert not any("unrelated" in t.lower() for t in journal_titles)

    store_pkg._local_stores.clear()


@pytest.mark.asyncio
async def test_gather_events_respects_cursor(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))

    import br8n.store as store_pkg
    import br8n.livingdocs.notes as notes_mod

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.livingdocs.timeline import _gather_events

    ctx = resolve_tenant("proj", "main", create=True)
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# Old\n\nold body", session_id="s1", title="Old",
    )
    all_events = await _gather_events(ctx, project="proj", since=None)
    assert all_events
    newest = max((e.ts, e.id) for e in all_events)
    # cursor at the newest event → nothing newer
    fresh = await _gather_events(ctx, project="proj", since=newest)
    assert fresh == []

    store_pkg._local_stores.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_gather.py -v`
Expected: FAIL — `ImportError: cannot import name '_gather_events'`

- [ ] **Step 3: Implement `_gather_events`**

Append to `backend/br8n/livingdocs/timeline.py`:

```python
# --- event gathering (store-backed, best-effort per source) ------------------

def _is_newer(ts: str, fid: str, since: tuple[str, str] | None) -> bool:
    return since is None or (ts, fid) > since


def _first_line(text: str) -> str:
    """First non-empty, non-H1 line of a finding body — used as a one-line gist."""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("# "):
            continue
        return line[:200]
    return ""


def _events_from_kb(
    store, kb_id: str, kind: str, category: str, since: tuple[str, str] | None
) -> list[TimelineEvent]:
    """Collect events of one `category` from one KB. Best-effort: [] on any error."""
    out: list[TimelineEvent] = []
    try:
        listed = store.list_findings(kb_id, category=category)
        rows = listed.get("findings", []) if isinstance(listed, dict) else []
    except Exception:  # noqa: BLE001 — a missing/unreadable source is skipped
        return out
    for row in rows:
        fid = row.get("id")
        ts = row.get("created_at") or ""
        if not fid or not _is_newer(ts, fid, since):
            continue
        try:
            full = store.get_finding(kb_id, fid)
        except Exception:  # noqa: BLE001 — skip a single unreadable finding
            full = {}
        title = (full.get("title") or row.get("title") or "").strip()
        gist = full.get("hypothesis") or _first_line(full.get("content", ""))
        out.append(TimelineEvent(ts=ts, kind=kind, title=title or "(untitled)",
                                  gist=gist, id=fid))
    return out


def _journal_events(
    project: str, since: tuple[str, str] | None
) -> list[TimelineEvent]:
    """Journal entries (JOURNAL_SCOPE KB) stamped with this `project`. Best-effort."""
    out: list[TimelineEvent] = []
    try:
        jctx = resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=False)
        store = get_store(jctx.access_token, org_id=jctx.org_id)
        listed = store.list_findings(jctx.kb_id, category="journal")
        rows = listed.get("findings", []) if isinstance(listed, dict) else []
    except Exception:  # noqa: BLE001 — no journal yet / backend error → none
        return out
    for row in rows:
        fid = row.get("id")
        ts = row.get("created_at") or ""
        if not fid or not _is_newer(ts, fid, since):
            continue
        try:
            full = store.get_finding(jctx.kb_id, fid)
        except Exception:  # noqa: BLE001
            full = {}
        prov = full.get("provenance") or row.get("provenance") or []
        if not any((p or {}).get("project") == project for p in prov):
            continue
        title = (full.get("title") or row.get("title") or "").strip()
        tags = full.get("tags") or []
        gist = next((t for t in tags if t not in ("journal",)), "") or \
            _first_line(full.get("content", ""))
        out.append(TimelineEvent(ts=ts, kind="journal", title=title or "(untitled)",
                                 gist=gist, id=fid))
    return out


async def _gather_events(
    ctx: TenantContext, *, project: str, since: tuple[str, str] | None
) -> list[TimelineEvent]:
    """All events newer than `since`, sorted ascending by (ts, id). Best-effort."""
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    events: list[TimelineEvent] = []
    events += _events_from_kb(store, ctx.kb_id, "note", "note", since)
    events += _events_from_kb(store, ctx.kb_id, "capture", "snapshot", since)
    events += _journal_events(project, since)
    events.sort(key=_sort_key)
    return events
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_gather.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/br8n/livingdocs/timeline.py backend/tests/test_timeline_gather.py
git commit -m "feat(timeline): gather notes+captures+journal events with cursor"
```

---

### Task 6: `run_timeline` orchestration + gated LLM day-headers

**Files:**
- Modify: `backend/br8n/livingdocs/timeline.py` (add `_infer_day_headers`, `run_timeline`)
- Test: `backend/tests/test_timeline_run.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_timeline_run.py`:

```python
import hashlib

import pytest

DIM = 1536


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


@pytest.mark.asyncio
async def test_run_timeline_appends_and_regenerates(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BR8N_TIMELINE_LLM", "0")  # deterministic day-headers

    import br8n.store as store_pkg
    import br8n.livingdocs.notes as notes_mod

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.livingdocs.paths import DocPaths
    from br8n.livingdocs.state import load_timeline_state
    from br8n.livingdocs.timeline import run_timeline

    ctx = resolve_tenant("proj", "main", create=True)
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# First note\n\nDecided the cursor design.",
        session_id="s1", title="First note",
    )

    res = await run_timeline(ctx, project="proj", project_path=str(tmp_path), kb="main")
    assert res["appended"] == 1

    p = DocPaths(project_path=str(tmp_path), kb="main")
    all_time = (p.timeline_dir / "all-time.md").read_text()
    assert "# Activity — proj/main" in all_time
    assert "First note" in all_time
    assert (p.timeline_dir / "recent.md").exists()
    assert (p.timeline_dir / "week.md").exists()

    # cursor advanced + counter reset
    st = load_timeline_state(p)
    assert st.last_event_ts != ""
    assert st.events_since_pass == 0
    assert st.last_pass_at != ""

    # second pass with no new events appends nothing, doesn't rewrite all-time
    before = all_time
    res2 = await run_timeline(ctx, project="proj", project_path=str(tmp_path), kb="main")
    assert res2["appended"] == 0
    assert (p.timeline_dir / "all-time.md").read_text() == before

    store_pkg._local_stores.clear()


@pytest.mark.asyncio
async def test_run_timeline_best_effort_on_bad_store(tmp_path, monkeypatch):
    """A failure inside the pass returns {'appended': 0}, never raises."""
    import br8n.livingdocs.timeline as tl

    async def _boom(*a, **k):
        raise RuntimeError("store down")

    monkeypatch.setattr(tl, "_gather_events", _boom)
    from br8n.agent.state import TenantContext

    ctx = TenantContext(user_id="local", org_id="local", project_id="p",
                        kb_id="k", thread_id="t", access_token="")
    res = await tl.run_timeline(ctx, project="p", project_path=str(tmp_path), kb="main")
    assert res == {"appended": 0}
```

(`TenantContext` is a dataclass with fields `user_id, org_id, project_id, kb_id,
thread_id, access_token` — verified in `backend/br8n/agent/state.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_run.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_timeline'`

- [ ] **Step 3: Implement `_infer_day_headers` + `run_timeline`**

Append to `backend/br8n/livingdocs/timeline.py`:

```python
# --- gated LLM day-headers (window views only) -------------------------------

class _DayHeaders(BaseModel):
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Map of YYYY-MM-DD → a SHORT one-line summary of that day",
    )


_DAY_SYSTEM = (
    "You summarize a developer's day of activity into ONE short line (<= 12 words),\n"
    "present tense, no trailing period. Given events grouped by date, return JSON\n"
    '{"headers": {"YYYY-MM-DD": "short summary", ...}} with one entry per date.'
)


async def _infer_day_headers(events: list[TimelineEvent]) -> dict[str, str]:
    """One-line LLM summary per day for the window views. Gated + best-effort.

    `BR8N_TIMELINE_LLM=0` (or any failure) → ``{}`` (callers fall back to plain
    dividers). Mirrors ``distill._infer_topics``."""
    if not events or os.getenv("BR8N_TIMELINE_LLM", "1") == "0":
        return {}
    by_day: dict[str, list[str]] = {}
    for e in events:
        by_day.setdefault(_event_day(e), []).append(f"{e.kind}: {e.title} — {e.gist}")
    user = "\n".join(
        f"{day}:\n" + "\n".join(f"  - {x}" for x in items)
        for day, items in sorted(by_day.items())
    )
    cfg = get_config().living_docs
    try:
        result = await structured_completion(
            model=cfg.distill_model,
            response_format=_DayHeaders,
            system=_DAY_SYSTEM,
            user=user,
            temperature=cfg.temperature,
            fallback_model=cfg.distill_fallback_model,
            use_json_schema=False,
        )
        return {str(k): str(v).strip() for k, v in (result.headers or {}).items()}
    except Exception as exc:  # noqa: BLE001 — day headers are best-effort
        logger.warning("timeline day-header inference failed (%s); plain dividers", exc)
        return {}


# --- the pass (best-effort) --------------------------------------------------

def _window_events(events: list[TimelineEvent], days: int, now: datetime) -> list[TimelineEvent]:
    cutoff = (now - timedelta(days=days)).isoformat()
    return [e for e in events if e.ts >= cutoff]


async def run_timeline(
    ctx: TenantContext, *, project: str, project_path: str, kb: str
) -> dict:
    """Append new events to all-time.md and regenerate recent.md/week.md.

    Best-effort: any failure logs and returns ``{"appended": 0}`` (never raises)."""
    if os.getenv("BR8N_TIMELINE", "1") == "0":
        return {"appended": 0}
    try:
        cfg = get_config().living_docs
        paths = DocPaths(project_path=project_path, kb=kb)
        st = load_timeline_state(paths)
        cursor = (st.last_event_ts, st.last_event_id) if st.last_event_ts else None

        # 1) append-only all-time log (cursor-bounded)
        new_events = await _gather_events(ctx, project=project, since=cursor)
        new_day = append_all_time(
            paths, project, kb, new_events, last_appended_day=st.last_appended_day
        )

        # 2) regenerate the two window views from a fresh windowed read
        now = datetime.now(timezone.utc)
        window_all = await _gather_events(ctx, project=project, since=None)
        recent = _window_events(window_all, cfg.recent_days, now)
        week = _window_events(window_all, cfg.week_days, now)
        headers = await _infer_day_headers(week)  # one call covers both windows
        ensure_layout(paths)
        paths.timeline_dir.mkdir(parents=True, exist_ok=True)
        (paths.timeline_dir / "recent.md").write_text(
            render_window("recent", recent, day_headers=headers)
        )
        (paths.timeline_dir / "week.md").write_text(
            render_window("week", week, day_headers=headers)
        )

        # 3) advance state
        if new_events:
            last = new_events[-1]
            st.last_event_ts = last.ts
            st.last_event_id = last.id
            st.last_appended_day = new_day
        st.events_since_pass = 0
        st.last_pass_at = now.isoformat()
        save_timeline_state(paths, st)

        logger.info("timeline: appended %s events (kb=%s)", len(new_events), kb)
        return {
            "appended": len(new_events),
            "recent_days": cfg.recent_days,
            "week_days": cfg.week_days,
            "all_time_path": str(paths.timeline_dir / "all-time.md"),
            "recent_path": str(paths.timeline_dir / "recent.md"),
            "week_path": str(paths.timeline_dir / "week.md"),
        }
    except Exception:  # noqa: BLE001 — best-effort: must never break a session
        logger.exception("timeline pass failed for kb=%s", kb)
        return {"appended": 0}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_run.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/br8n/livingdocs/timeline.py backend/tests/test_timeline_run.py
git commit -m "feat(timeline): run_timeline pass + gated LLM day-headers"
```

---

### Task 7: `schedule_timeline` (debounced, fire-and-forget)

**Files:**
- Modify: `backend/br8n/livingdocs/timeline.py` (add `_BG_TASKS`, `schedule_timeline`)
- Test: `backend/tests/test_timeline_schedule.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_timeline_schedule.py`:

```python
import asyncio

import pytest


def test_schedule_timeline_gated_off_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_TIMELINE", "0")
    from br8n.agent.state import TenantContext
    from br8n.livingdocs.paths import DocPaths
    from br8n.livingdocs.state import load_timeline_state
    from br8n.livingdocs.timeline import schedule_timeline

    ctx = TenantContext(user_id="local", org_id="local", project_id="p",
                        kb_id="k", thread_id="t", access_token="")
    schedule_timeline(ctx, project="p", project_path=str(tmp_path), kb="main")
    # counter not bumped, no state file written
    st = load_timeline_state(DocPaths(project_path=str(tmp_path), kb="main"))
    assert st.events_since_pass == 0


@pytest.mark.asyncio
async def test_schedule_timeline_bumps_and_fires(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_TIMELINE", "1")
    monkeypatch.setenv("BR8N_LIVING_DOCS", "1")

    import br8n.livingdocs.timeline as tl

    fired = {"n": 0}

    async def _fake_run(ctx, *, project, project_path, kb):
        fired["n"] += 1
        return {"appended": 0}

    monkeypatch.setattr(tl, "run_timeline", _fake_run)
    # debounce_n=1 → first event trips immediately
    monkeypatch.setattr(
        tl, "get_config",
        lambda: type("C", (), {"living_docs": type("L", (), {
            "timeline_debounce_n": 1, "timeline_debounce_minutes": 60})()})(),
    )

    from br8n.agent.state import TenantContext

    ctx = TenantContext(user_id="local", org_id="local", project_id="p",
                        kb_id="k", thread_id="t", access_token="")
    tl.schedule_timeline(ctx, project="p", project_path=str(tmp_path), kb="main")
    await asyncio.sleep(0)  # let the created task run
    # drain any scheduled tasks
    for t in list(tl._BG_TASKS):
        await t
    assert fired["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_schedule.py -v`
Expected: FAIL — `ImportError: cannot import name 'schedule_timeline'`

- [ ] **Step 3: Implement `schedule_timeline`**

Append to `backend/br8n/livingdocs/timeline.py`:

```python
# --- scheduling (debounced, fire-and-forget, best-effort) --------------------

_BG_TASKS: set[asyncio.Task] = set()


def schedule_timeline(
    ctx: TenantContext, *, project: str, project_path: str, kb: str
) -> None:
    """Bump the pending-event counter and, if the debounce trips, fire a pass.

    No-op when ``BR8N_LIVING_DOCS=0`` or ``BR8N_TIMELINE=0``. Mirrors
    ``distill.schedule_distill``: holds a strong task ref in ``_BG_TASKS``.
    Best-effort — no running event loop (or any error) silently no-ops."""
    if os.getenv("BR8N_LIVING_DOCS", "1") == "0":
        return
    if os.getenv("BR8N_TIMELINE", "1") == "0":
        return
    try:
        cfg = get_config().living_docs
        paths = DocPaths(project_path=project_path, kb=kb)
        st = load_timeline_state(paths)
        st.events_since_pass += 1
        save_timeline_state(paths, st)
        if not should_roll(
            st,
            debounce_n=cfg.timeline_debounce_n,
            debounce_minutes=cfg.timeline_debounce_minutes,
        ):
            return
        task = asyncio.create_task(
            run_timeline(ctx, project=project, project_path=project_path, kb=kb)
        )
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
    except Exception:  # noqa: BLE001 — scheduling is best-effort (e.g. no event loop)
        logger.debug("timeline schedule skipped", exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_schedule.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/br8n/livingdocs/timeline.py backend/tests/test_timeline_schedule.py
git commit -m "feat(timeline): schedule_timeline debounced fire-and-forget"
```

---

### Task 8: MCP tool `br8n_timeline` + trigger wiring

**Files:**
- Modify: `backend/br8n/interfaces/mcp/server.py` (import, `_timeline_impl`, tool, wire into `_note_impl` + `_capture_impl`)
- Modify: `backend/br8n/livingdocs/fallback.py` (wire after `persist_note`)
- Test: `backend/tests/test_timeline_tool.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_timeline_tool.py` (mirrors `test_distill_tool.py`):

```python
import hashlib

import pytest

DIM = 1536


def _fake_vec(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


@pytest.mark.asyncio
async def test_timeline_tool_force_builds(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BR8N_TIMELINE_LLM", "0")

    import br8n.store as store_pkg
    import br8n.livingdocs.notes as notes_mod

    store_pkg._local_stores.clear()
    monkeypatch.setattr(notes_mod, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(notes_mod, "schedule_rebuild", lambda ctx: None)

    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.livingdocs.notes import persist_note
    from br8n.interfaces.mcp.server import _timeline_impl

    ctx = resolve_tenant("proj", "main", create=True)
    await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content="# n\n\nbody", session_id="s1", title="n",
    )
    res = await _timeline_impl("proj", "main", str(tmp_path), force=True)
    assert res["forced"] is True
    assert res["appended"] == 1
    assert res["project"] == "proj"

    store_pkg._local_stores.clear()


@pytest.mark.asyncio
async def test_timeline_tool_no_force_schedules(tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "brain.db"))

    import br8n.store as store_pkg
    store_pkg._local_stores.clear()

    from br8n.interfaces.mcp.server import _timeline_impl

    res = await _timeline_impl("proj", "main", str(tmp_path), force=False)
    assert res["forced"] is False
    assert res["scheduled"] is True

    store_pkg._local_stores.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_tool.py -v`
Expected: FAIL — `ImportError: cannot import name '_timeline_impl'`

- [ ] **Step 3: Wire the imports + impl + tool in `server.py`**

In `backend/br8n/interfaces/mcp/server.py`, find the distill import (line 36):

```python
from br8n.livingdocs.distill import run_distill, schedule_distill
```

Add immediately after it:

```python
from br8n.livingdocs.timeline import run_timeline, schedule_timeline
```

In `_note_impl`, after the existing `schedule_distill(ctx, project_path=project_path, kb=kb)`
(line 101), add:

```python
    schedule_timeline(ctx, project=project, project_path=project_path, kb=kb)
```

In `_capture_impl`, after `schedule_activity_update(snap, finding_id)` (line 83), add:

```python
    schedule_timeline(ctx, project=project, project_path=project_path, kb=kb)
```

Then add the impl + tool next to the distill ones (after `br8n_distill`, ~line 171):

```python
async def _timeline_impl(project, kb, project_path, force=False):
    ctx = resolve_tenant(project, kb, create=True)
    if force:
        res = await run_timeline(ctx, project=project, project_path=project_path, kb=kb)
        return {"forced": True, **res, "project": project, "kb": kb}
    schedule_timeline(ctx, project=project, project_path=project_path, kb=kb)
    return {"forced": False, "scheduled": True, "project": project, "kb": kb}


@mcp.tool()
async def br8n_timeline(project: str, kb: str, project_path: str, force: bool = False) -> dict:
    """(Re)build the append-only activity timeline at .br8n/timeline/ from this
    repo+branch's notes + captures + journal. `force=True` runs a pass now and returns
    {forced, appended, recent_days, week_days, *_path}; otherwise it nudges the debounced
    background rollup. Used by /br8n:timeline --rebuild."""
    return await _timeline_impl(project, kb, project_path, force)
```

- [ ] **Step 4: Wire into `fallback.py`**

`distill_fallback_note(ctx, *, project_path, kb, session_id, max_snaps=8)` has **no**
`project` parameter, so derive it from `project_path` (the repo root) the same way the
rest of the codebase does (`os.path.basename` — see `watch.derive_project_kb`).
`fallback.py` already imports `os`.

Add the import near the other livingdocs imports at the top of the file:

```python
from br8n.livingdocs.timeline import schedule_timeline
```

Then change the `return await persist_note(...)` block (lines 178-186) to capture the
result, schedule (deriving `project`), and return:

```python
        res = await persist_note(
            ctx,
            project_path=project_path,
            kb=kb,
            content=content,
            session_id=session_id,
            title=title,
            source="backend",
        )
        project = os.path.basename(os.path.normpath(project_path))
        schedule_timeline(ctx, project=project, project_path=project_path, kb=kb)
        return res
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_tool.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Run the full livingdocs/server test slice (regression)**

Run: `cd backend && .venv/bin/pytest tests/test_timeline_state.py tests/test_timeline_render.py tests/test_timeline_gather.py tests/test_timeline_run.py tests/test_timeline_schedule.py tests/test_timeline_tool.py tests/test_distill_tool.py tests/test_note_tool.py tests/test_livingdocs_fallback.py -v`
Expected: PASS (existing distill/note/fallback tests still green)

- [ ] **Step 7: Commit**

```bash
git add backend/br8n/interfaces/mcp/server.py backend/br8n/livingdocs/fallback.py backend/tests/test_timeline_tool.py
git commit -m "feat(timeline): br8n_timeline MCP tool + schedule wiring (note/capture/fallback)"
```

---

### Task 9: `/br8n:timeline` skill

**Files:**
- Create: `backend/../skills/timeline/SKILL.md` → actual path `skills/timeline/SKILL.md` (repo root)

No automated test — verified by reading. Mirror `skills/docs/SKILL.md` structure.

- [ ] **Step 1: Create the skill file**

Create `skills/timeline/SKILL.md`:

```markdown
---
name: timeline
description: Read back your append-only activity timeline for this repo+branch — a chronological log of session notes, context captures, and journal entries. Shows recent activity (last few days) by default, with the past-week view and the full all-time scroll alongside. Pass `--rebuild` to force a fresh rollup now. Use when the user asks "what have I been doing", wants a chronological work log, a daily/weekly recap, or to scroll their activity history.
---

# br8n — Timeline (append-only activity log)

br8n periodically rolls this repo+branch's **session notes**, **context captures**, and
**journal entries** into a chronological, append-only timeline at
`<project_path>/.br8n/timeline/`:

- `all-time.md` — the canonical append-only log (newest at the bottom, never rewritten).
- `recent.md` — the last few days (regenerated each pass).
- `week.md` — the past week (regenerated each pass).

This is the **temporal** view — distinct from `/br8n:docs` (the topical doc tree) and
`/br8n:activity` (the cross-repo work graph). The files are git-ignored and regenerated;
never hand-edit them — they rebuild from notes/captures/journal.

## Step 0 — Resolve target

`project` = git repo basename, `kb` = git branch, `project_path` = repo root
(see [`../_shared/preamble-first.md`](../_shared/preamble-first.md)):

```bash
basename "$(git rev-parse --show-toplevel)"   # project
git branch --show-current                     # kb
git rev-parse --show-toplevel                 # project_path
```

No prior tap needed — the timeline is plain files in the working tree.

## Step 1 — Read and present

The timeline files are markdown on disk under `<project_path>/.br8n/timeline/`. Read
them with your **own** file tools — no MCP call needed to read:

1. `Read` `<project_path>/.br8n/timeline/recent.md` and present it (newest at the
   bottom — the "scrolling down" feel).
2. Point the user at the wider views: `week.md` (past week) and `all-time.md` (the full
   scroll). `Read` and surface those too if the user asks for more history.

If the dir is **empty or missing**, say so and offer `--rebuild` (Step 2) to build it
from the notes/captures/journal so far.

## Step 2 — `--rebuild` (force a pass)

Trigger when the user passes `--rebuild`, or when the dir is empty/stale. Call:

```
mcp__plugin_br8n_br8n__br8n_timeline(
  project, kb, project_path, force=true
)
```

It returns `{forced, appended, recent_days, week_days, all_time_path, recent_path,
week_path}`. Report `appended` (how many new events landed in the all-time log) and the
window sizes, then **re-read** `recent.md` (Step 1) and present the refreshed view.

Without `--rebuild` this skill only reads; the rollup otherwise happens on its own in the
background after notes/captures (debounced) — you don't need to nudge it.
```

- [ ] **Step 2: Verify the file reads correctly**

Run: `sed -n '1,5p' skills/timeline/SKILL.md`
Expected: shows the YAML frontmatter `name: timeline`.

- [ ] **Step 3: Commit**

```bash
git add skills/timeline/SKILL.md
git commit -m "feat(timeline): /br8n:timeline skill"
```

---

### Task 10: Docs — CLAUDE.md + .env.example

**Files:**
- Modify: `CLAUDE.md` (MCP-tool table, skills list, `.br8n/` layout note, gate list)
- Modify: `backend/.env.example` (document the two gates, if the file documents gates)

No automated test — verified by reading.

- [ ] **Step 1: Update the MCP tools table in `CLAUDE.md`**

In the "MCP tools (for Claude Code)" table, add a row after `br8n_activity`:

```markdown
| `br8n_timeline` | (Re)build the append-only activity timeline (`.br8n/timeline/`) from notes+captures+journal |
```

- [ ] **Step 2: Update the skills tree in `CLAUDE.md`**

In the `skills/` code block, add after the `activity/SKILL.md` line:

```
  timeline/SKILL.md           /br8n:timeline — the append-only activity log (recent/week/all-time)
```

- [ ] **Step 3: Add a Phase-status / feature note in `CLAUDE.md`**

Under "Phase status", add a new bullet:

```markdown
- [x] Activity timeline — per-repo+branch append-only chronological log of
  notes+captures+journal. `all-time.md` (append-only) + regenerated `recent.md`/
  `week.md` window views at `.br8n/timeline/`. Background, debounced, cursor-driven
  (mirrors the doc-tree distill); surfaces: `br8n_timeline` MCP tool + `/br8n:timeline`
  skill. Gates: `BR8N_TIMELINE` (master), `BR8N_TIMELINE_LLM` (window day-headers).
  Design + plan: `docs/plans/2026-06-07-timeline-{design,plan}.md`.
```

- [ ] **Step 4: Document the gates in `backend/.env.example`**

Read `backend/.env.example`; locate where `BR8N_LIVING_DOCS` / `BR8N_ACTIVITY_KG`
gates are documented (if present). Add nearby:

```
# Activity timeline (append-only .br8n/timeline/ log). Default on.
# BR8N_TIMELINE=1
# BR8N_TIMELINE_LLM=1   # LLM one-line day-headers in the recent/week views
```

If `.env.example` does not document feature gates at all, skip this step (don't
introduce a new convention) and note it in the commit message.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md backend/.env.example
git commit -m "docs(timeline): CLAUDE.md tool/skill/gate entries + .env.example gates"
```

---

### Task 11: Full suite + finish

**Files:** none (verification)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS — all green (new timeline tests + existing suite unaffected).

- [ ] **Step 2: Smoke the local-tier server import**

Run: `cd backend && .venv/bin/python -c "import br8n.interfaces.mcp.server as s; print('br8n_timeline' in dir(s))"`
Expected: prints `True`.

- [ ] **Step 3: Invoke the finishing-a-development-branch skill**

Use `superpowers:finishing-a-development-branch` to decide how to integrate the
`feat/timeline` branch (merge / PR / cleanup).

---

## Self-review notes (author)

- **Spec coverage:** every spec section maps to a task — config (T1), paths (T2), state/cursor (T3), event carrier + rendering split incl. plain dividers vs LLM headers (T4/T6), three sources incl. journal `provenance.project` filter (T5), `run_timeline` append+regenerate (T6), `schedule_timeline` + wiring incl. `fallback.py` (T7/T8), `br8n_timeline` tool (T8), skill (T9), docs+gates (T10), testing strategy (T1–T8 tests + T11 suite). YAGNI items (cross-repo feed, HTML, retroactive headers) are absent by construction.
- **Type consistency:** `TimelineEvent(ts, kind, title, gist, id)`, `TimelineState` fields, `append_all_time(... last_appended_day=)` → returns the new day, `render_window(name, events, *, day_headers)`, `run_timeline(ctx, *, project, project_path, kb)`, `schedule_timeline(ctx, *, project, project_path, kb)`, `_timeline_impl(project, kb, project_path, force)` — names are identical across tasks.
- **Resolved (previously open) details:** (a) `TenantContext` dataclass fields are `user_id, org_id, project_id, kb_id, thread_id, access_token` — test constructions use these; (b) `distill_fallback_note` has no `project` param, so the `fallback.py` wiring derives `project = os.path.basename(os.path.normpath(project_path))` (matches `watch.derive_project_kb`).
```
