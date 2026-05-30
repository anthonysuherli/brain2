# brain2 statusline — resume-cue redesign

**Date:** 2026-05-30
**Status:** Approved, ready to implement

## Goal

Replace the current cross-branch portfolio statusline with a single-focus
**resume cue**: tell the developer what they were doing on the *current* branch
and whether they can still trust that captured context — in two lines, always
fast, never failing.

## Layout

```
🧠 {project} ▶ {branch}  "{hypothesis}"
   {verdict glyph} {trust bar}
```

Line 1 — identity + intent (hypothesis truncated to terminal-width budget).
Line 2 — state-adaptive trust bar (verdict, age, drift glyphs, action hint).

## Four states

| State | Trigger | Line 2 |
|---|---|---|
| NO_CAPTURE | No snapshot exists for this branch | `⚡ no capture yet · /brain2:capture to anchor` |
| FRESH | Age < STALE_AGE AND drift is low | `✓ fresh · captured 4m ago · ╓0` |
| DRIFTED | commits_since ≥ 1 OR moved_files ≥ DRIFT_FILES_WARN | `⚠ drifted · 18m ago · ╓5 ⎇1 · /resume to rebuild` |
| IDLE | Age ≥ IDLE_AGE AND tree clean AND commits_since == 0 | `· idle 3d` (with echoed `last: "…"` only if hypothesis was truncated) |

State priority: DRIFTED is checked before IDLE/FRESH (advancing but old = drifted,
not idle).

## Drift computation

Two signals, both derived from data brain2 already stores:

**Signal A — working-set drift:**
```
captured_files = paths from snapshot's **Git diff stat** block
current_files  = paths from `git diff --stat` run now
moved          = symmetric_difference(captured_files, current_files)
```
Counts files that entered or left the changed-set — robust to line-count noise.

**Signal B — commits since capture:**
```
commits_since = git rev-list --count --since="{captured_at}" HEAD
```
Catches "I committed and moved on" — `git diff` shrinks when you commit, but work
has still advanced past the snapshot.

**Tunable consts (top of file):**
```python
DRIFT_FILES_WARN = 2       # ≥2 files moved → drifted
STALE_AGE        = 30 * 60 # 30m: fresh threshold
IDLE_AGE         = 24 * 3600  # 1d: idle threshold
```

## Glyph legend

- `╓N` — N files moved in/out of changed-set (omitted when 0)
- `⎇N` — N commits since capture (omitted when 0)
- ASCII fallbacks (`fN`, `cN`) when `LANG`/`LC_*` lacks `UTF-8`

## Action-hint routing

| State | Action hint |
|---|---|
| NO_CAPTURE | `/brain2:capture to anchor` |
| DRIFTED | `/resume to rebuild` |
| FRESH | (none — nothing to do) |
| IDLE | (none — quiet, don't nag) |

## Width handling

- Read terminal width from stdin JSON; derive `hyp_budget = width − badge/branch overhead`, clamped `[20, 60]`.
- Fall back to fixed `HYP_WIDTH = 38` when width is absent.
- Line 2 only truncates the IDLE `last: "…"` echo; all other components are short by construction.

## Architecture

**What changes:** query narrows to current branch only; drift module added (pure
functions); portfolio renderer replaced by two-line state renderer.

**What's reused verbatim:** `git()`, `load_env()`, `resolve_tier()`, `db_path()`,
cloud disk-cache mechanism, `age()`, `truncate()`, ANSI consts, never-fail wrapper.

**Degradation ladder** (every new step wrapped so failure drops one level):
```
drift fails           → render FRESH/IDLE from age alone (drop ╓/⎇ glyphs)
snapshot fetch fails  → render line 1 only (badge + branch), no line 2
git root absent       → print nothing, exit 0
top-level except      → exit 0
```

New git subprocesses (diff + rev-list) keep the existing 2s timeout. Cloud keeps
1.5s timeout + stale-cache fallback. Net added latency: <50ms (both local ops).

## Backward compatibility

Old portfolio renderer preserved behind `BRAIN2_STATUSLINE=portfolio` env flag
for one version, then removed.

## Files touched

- `scripts/brain2-statusline.py` — main rewrite
- `scripts/test_statusline.py` (new) — unit + integration tests

## Tests

**Unit (pure functions):**
- `parse_diff_stat_block(content)` — handles truncated content, `+N more` lines
- `compute_drift(captured, current, commits_since)` — all threshold boundaries
- `classify(...)` — all 4 states, DRIFTED-beats-IDLE ordering
- `render_line2(state, ...)` — glyph vs ASCII, IDLE dedupe, per-state action hints

**Integration (tmpdir git repo + temp SQLite DB):**
- Local tier end-to-end: real git ops, snapshot row in SQLite, assert 2-line output
- Cloud tier: mocked urllib, same render assertions

**Never-fail assertions:** garbage stdin, non-git cwd, corrupt diff block, git absent → exit 0.
