# `/br8n:timeline` — append-only activity timeline (design)

Status: **design** (2026-06-07). Awaiting implementation plan (writing-plans).

```
notes ─┐
captures ─┼─► run_timeline ─► append all-time.md (cursor-bounded, never rewritten)
journal ─┘                  └─► regenerate recent.md / week.md (windowed, LLM day-headers)
                ▲
   schedule_timeline (debounced, fire-and-forget) ◄── persist_note / persist_snapshot
```

## Problem

br8n already turns session notes into two things: a **topical** doc tree
(`livingdocs/distill.py` → `.br8n/docs/`) and a cross-repo **activity graph**
(`knowledge_graph/activity.py`). Neither gives a plain **chronological** read of
"what have I been doing here lately." This feature adds a **temporal** rollup: a
periodically-updated, append-only activity timeline per repo+branch, plus two
regenerated time-window views.

This is distinct from — and does not replace — the topical doc tree or the activity
graph. It is a third, time-ordered surface built from the same Findings.

## Decisions (locked during brainstorming)

- **Name**: `/br8n:timeline` — skill `skills/timeline/SKILL.md`, MCP tool
  `br8n_timeline`. Rejected `/br8n:tap`: collides with delapan's `tap`
  (= KB question→answer) and br8n's existing `resume`/`pickup`.
- **Doc model**: `all-time.md` is the **canonical append-only log** — it only ever
  grows, newest events appended at the bottom, never rewritten. `recent.md` (last
  `recent_days`) and `week.md` (last `week_days`) are **regenerated-each-pass views**
  over the tail of the same event stream.
- **Entry content**: hybrid. Each event renders as a deterministic line, grouped by
  day. An **LLM one-line day-header** is applied **only in the regenerated window
  views** (`recent.md` / `week.md`), where re-rendering a whole day each pass is
  coherent. The append-only `all-time.md` uses plain `## YYYY-MM-DD` dividers — a day
  isn't "done" when its first events are appended, and the log is never rewritten.
- **Sources**: notes (`category="note"`) + captures (`category="snapshot"`) in this
  KB, plus journal (`category="journal"` in the `JOURNAL_SCOPE` KB, filtered to
  `provenance.project == project`).
- **Scope**: per repo+branch. Files live in `<project_path>/.br8n/timeline/`, mirroring
  where the doc tree and notes already live.
- **Trigger**: background, debounced, fire-and-forget (mirrors `schedule_distill`).
  A **cursor** in `TimelineState` means the trigger only decides *when* a pass runs;
  the pass reads **all** new events since the cursor, so events created by background
  hooks (Stop-hook session notes via `fallback.py`, commit-hook captures via
  `watch.py`) get swept in on the next pass regardless of what triggered it.
- **Gates**: `BR8N_TIMELINE` (feature master), `BR8N_TIMELINE_LLM` (day-headers),
  both default on; both also gated by the existing `BR8N_LIVING_DOCS` master.

## Module layout

All new/changed code is in `backend/br8n/livingdocs/`, mirroring `distill.py` and
`knowledge_graph/activity.py` conventions (module-level `_BG_TASKS`, env gates,
best-effort `try/except` that never breaks a session).

| File | Change |
|---|---|
| `livingdocs/timeline.py` | **new** — `run_timeline()` builder + `schedule_timeline()` scheduler + internal `TimelineEvent` carrier and rendering helpers |
| `livingdocs/paths.py` | extend `DocPaths` — `timeline_dir`, `timeline_state_path` |
| `livingdocs/state.py` | add `TimelineState`, `load_timeline_state`, `save_timeline_state`, `should_roll` |
| `config.py` (`LivingDocsConfig`) | add timeline knobs (below) |
| `interfaces/mcp/server.py` | new `br8n_timeline` tool; call `schedule_timeline` in `_note_impl` (after `schedule_distill`) and in `_capture_impl` (after `schedule_activity_update`) |
| `livingdocs/fallback.py` | call `schedule_timeline` after the session-note persist |
| `skills/timeline/SKILL.md` | **new** — `/br8n:timeline` skill |
| `CLAUDE.md` | update MCP-tool table, skills list, `.br8n/` layout, gate list |

## Config additions (`LivingDocsConfig`)

```python
timeline_dirname: str = "timeline"
timeline_state_filename: str = "timeline-state.json"
timeline_debounce_n: int = 3        # roll after N new events …
timeline_debounce_minutes: int = 60 # … or T minutes since last pass
recent_days: int = 3                # recent.md window
week_days: int = 7                  # week.md window
```

LLM day-headers reuse the existing `distill_model`, `distill_fallback_model`, and
`temperature` — no new model config.

## Paths (`.br8n/timeline/`)

`DocPaths` gains:
- `timeline_dir` → `root / cfg.timeline_dirname` (i.e. `.br8n/timeline/`)
- `timeline_state_path` → `root / cfg.timeline_state_filename`

Files written under `timeline_dir`:
- `all-time.md` — append-only log. On first creation, write a `# Activity —
  <project>/<kb>` H1 header. Thereafter, only appended to.
- `recent.md`, `week.md` — overwritten each pass.

`ensure_layout` already creates `.br8n/` with a self-ignoring `.gitignore` (`*`), so the
timeline dir is never committed; `timeline_dir.mkdir(parents=True, exist_ok=True)` is
called before writing.

## State (`TimelineState`)

```python
class TimelineState(BaseModel):
    last_event_ts: str = ""      # ISO ts of the most recently appended event (cursor)
    last_event_id: str = ""      # id of that event (tie-break on equal ts)
    last_appended_day: str = ""  # YYYY-MM-DD of the last line in all-time.md
    events_since_pass: int = 0   # debounce counter
    last_pass_at: str = ""       # ISO ts of last completed pass
```

`should_roll(state, *, debounce_n, debounce_minutes, now_iso=None)` mirrors
`should_distill`: `< 1` pending → never; `>= debounce_n` → now; else if a prior pass
exists, roll once `debounce_minutes` elapsed; unparseable timestamps → conservative
`False`. `load_timeline_state`/`save_timeline_state` mirror `load_state`/`save_state`
(default on missing/corrupt, never raise).

The cursor is `(last_event_ts, last_event_id)`: an event is "new" iff
`(ts, id) > (last_event_ts, last_event_id)` lexicographically. This tolerates multiple
events sharing an identical `created_at`.

## Event carrier (`TimelineEvent`)

```python
@dataclass
class TimelineEvent:
    ts: str            # ISO created_at
    kind: str          # "note" | "capture" | "journal"
    title: str
    gist: str          # one-line
    id: str
```

Construction per source (best-effort, per-source `try/except` — a failed or empty
source is skipped, not fatal):

- **note** — `store.list_findings(kb_id, category="note")`; for each, fetch the full
  record (list view omits `content`, same as `distill.run_distill`) → `gist` = first
  non-empty content line, trimmed.
- **capture** — `store.list_findings(kb_id, category="snapshot")` → `gist` = the
  snapshot hypothesis if present, else a short diff-stat summary (reuse the parsing
  already in `livingdocs/drift.py` if convenient, else the finding title).
- **journal** — resolve the journal KB via
  `resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE, create=False)` →
  `store.list_findings(journal_kb_id, category="journal")`, keep only entries whose
  `provenance[].project == project` → `gist` = the entry's `type` tag (insight /
  reflection / reference / decision) or first content line.

To keep passes cheap, only fetch full records for events newer than the cursor
(incremental). The windowed regeneration (recent/week) reads only the last
`week_days` of events, which is naturally bounded.

## `run_timeline(ctx, *, project, project_path, kb) -> dict`

Best-effort; wraps everything in `try/except` and returns `{"appended": 0}` on any
failure (must never break a session). Steps:

1. `load_timeline_state`.
2. Gather `TimelineEvent`s from all three sources with `(ts, id) > cursor`
   (per-source best-effort).
3. Sort ascending by `(ts, id)`.
4. **Append to `all-time.md`** (open in append mode; create with the H1 header if
   missing): for each new event, if `event_day != last_appended_day`, write a
   `## YYYY-MM-DD` divider first, then the event line. Update `last_appended_day` and
   advance the cursor to the last event's `(ts, id)`.
5. **Regenerate `recent.md` and `week.md`**: read events in
   `[now - recent_days, now]` and `[now - week_days, now]` from the same three
   sources (a fresh windowed read, *not* cursor-bounded); group by day; for each day,
   render an LLM one-line day-header (gated `BR8N_TIMELINE_LLM`; deterministic
   fallback = a plain `## YYYY-MM-DD`), then the day's event lines. Overwrite both
   files. Day-header LLM is one batched call (one summary line per day in the window),
   mirroring `distill._infer_topics` (same client, model config, best-effort fallback).
6. `save_timeline_state` (advance cursor + `last_appended_day`, reset
   `events_since_pass = 0`, stamp `last_pass_at`).
7. Return `{"appended": <n>, "recent_days": …, "week_days": …,
   "all_time_path": …, "recent_path": …, "week_path": …}`.

### Event line format

```
HH:MM · <kind> · <title> — <gist>
```

`<kind>` is a short label or glyph per source (e.g. `note` / `capture` / `journal`).
Newest at the bottom (ascending order) in every file, matching the "scrolling down"
feel.

## Scheduling (`schedule_timeline`)

Mirrors `schedule_distill` exactly:

```python
_BG_TASKS: set[asyncio.Task] = set()

def schedule_timeline(ctx, *, project, project_path, kb) -> None:
    if os.getenv("BR8N_LIVING_DOCS", "1") == "0": return
    if os.getenv("BR8N_TIMELINE", "1") == "0": return
    # load state, bump events_since_pass, save
    # if should_roll(...): create_task(run_timeline(...)) held in _BG_TASKS
    # best-effort: no event loop / any error → silent no-op
```

`run_timeline` itself short-circuits to `{"appended": 0}` when `BR8N_TIMELINE=0` so a
`force=true` MCP call also respects the gate.

**Wiring** (where to call `schedule_timeline`):
- `interfaces/mcp/server.py` — in `_note_impl` (after the existing `schedule_distill`,
  ~L101) and in `_capture_impl` (after `schedule_activity_update`, ~L83). The note
  tool and the capture tool are the two event-creating MCP entry points.
- `livingdocs/fallback.py` — after the backend session-note `persist_note` (the
  primary automatic note path).
- The `br8n_timeline` tool's own non-`force` path also calls `schedule_timeline`.

Because the pass is cursor-driven, these triggers only set the *cadence*; any event in
the store newer than the cursor is included whenever a pass next runs (or on
`--rebuild`).

## Surfaces

### MCP tool `br8n_timeline`

```
br8n_timeline(project: str, kb: str, project_path: str, force: bool = False) -> dict
```

- `force=False` (default): bump the debounce via `schedule_timeline` and report
  current state/paths (does **not** block on a pass).
- `force=True`: run `run_timeline` synchronously and return its result dict.

Mirrors `br8n_distill`. Registered in `interfaces/mcp/server.py`.

### Skill `skills/timeline/SKILL.md` (`/br8n:timeline`)

Follows the `/br8n:docs` pattern — the skill reads the markdown files in the working
tree with its **own** file tools (no MCP round-trip needed to read):

- **Step 0** — resolve `project` / `kb` / `project_path` (repo basename / branch /
  toplevel), per `_shared/preamble-first.md`.
- **Default (`/br8n:timeline`)** — `Read` `.br8n/timeline/recent.md` and present it
  (newest at bottom); point to `week.md` and `all-time.md`. If the dir is empty/missing,
  say so and offer `--rebuild`.
- **`--rebuild`** — call `br8n_timeline(project, kb, project_path, force=true)`, report
  `appended` + window sizes, then re-read and present `recent.md`.

No prior tap needed — the timeline files are plain working-tree files.

## Gates summary

| Env | Default | Effect when `0` |
|---|---|---|
| `BR8N_LIVING_DOCS` | on | Disables the whole living-docs subsystem (incl. timeline) |
| `BR8N_TIMELINE` | on | Disables timeline rollup specifically (distill/activity unaffected) |
| `BR8N_TIMELINE_LLM` | on | Day-headers fall back to plain `## YYYY-MM-DD` dividers in the window views |

## Testing strategy

Pure/deterministic units, no network:
- `should_roll` — count threshold, time threshold, never-rolled, unparseable ts
  (mirror the existing `should_distill` tests).
- Cursor advance + `(ts, id)` tie-break — events with identical `created_at`.
- `all-time.md` append semantics — day divider emitted only on day rollover; existing
  content preserved across passes (never rewritten); H1 header written once.
- Window rendering with `BR8N_TIMELINE_LLM=0` — deterministic plain dividers, correct
  events filtered into the 3-day vs 7-day windows.
- Journal source filter — only entries with matching `provenance.project` included.
- Best-effort — a raising source / unreadable finding is skipped, pass still completes;
  `run_timeline` never raises.

LLM day-header inference is gated and best-effort; tests run with the LLM gate off
(deterministic path), matching how `distill`/`activity` are tested.

## Out of scope (YAGNI)

- Cross-repo unified feed (a single `~/.br8n/` timeline across all repos) — explicitly
  deferred; this feature is per repo+branch.
- HTML rendering / any non-markdown surface.
- Retroactive LLM day-headers in the append-only `all-time.md`.
- Configurable per-entry templates or user-tunable line formats.
- A dedicated `/v1` API endpoint or iOS surface for the timeline.
```
