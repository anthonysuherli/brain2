# Commit-boundary-only auto-capture

**Date:** 2026-06-05
**Status:** Implemented

## Problem

The Living Docs auto-capture watcher polled every 180s and snapshotted on any drift
(≥2 tracked files moved OR ≥1 commit). During active work this fired frequently,
producing many near-duplicate snapshots and felt like "way too much."

## Decision

Cut auto-capture to **commit-boundary only**. Keep exactly two capture paths:

1. **On git commit** — the `post-commit` hook runs `br8n.livingdocs.watch --once`
   (`run_once`), which re-anchors a snapshot (a commit makes `commits_since >= 1`).
2. **On demand** — `/br8n:capture` (the `br8n_capture` MCP tool).

The continuous background watcher is removed entirely. This was a clean code
removal, not just an env-gate flip — `BR8N_AUTO_CAPTURE` / `BR8N_LIVING_DOCS`
gates remain and now gate the commit-hook install + the `run_once` path.

### Accepted tradeoff

During a long *uncommitted* editing session there is no auto-snapshot — the freshest
snapshot is from the last commit. Stepping away mid-edit before committing is covered
by the manual `/br8n:capture` path.

### Alternatives rejected

- **Fully manual** (remove the commit hook too) — loses the "never lose context"
  value for the common case (you commit regularly).
- **Tune the watcher** (longer interval + higher drift threshold) — still continuous
  churn; doesn't address the "snapshots while I'm mid-thought" complaint.

## Changes

- `hooks/auto-capture.py` — `main()` now only installs the `post-commit` hook
  (`should_install` / `install` / `install_post_commit_hook`). Removed the watcher
  spawn, the `.watch.stop` / `.watch.pid` bookkeeping (`paths_for`), `launch_watcher`,
  and `stop_watcher`.
- `hooks/auto-capture-stop.py` — deleted (no watcher to stop).
- `hooks/hooks.json` — removed the `SessionEnd → auto-capture-stop.py` entry; updated
  the description. `SessionStart → auto-capture.py` stays (now installs the commit hook).
- `backend/br8n/livingdocs/watch.py` — removed `run_watch`, `fingerprint`, `changed`,
  the non-`--once` `__main__` branch, and the now-unused `hashlib` / `time` /
  `get_config` imports. Kept `run_once`, `should_capture`, `capture_once`,
  `read_git_state`, `last_snapshot`, `derive_project_kb`.
- `backend/br8n/config.py` — removed `LivingDocsConfig.watch_interval_seconds`.
- Tests — `tests/hooks/test_auto_capture_hook.py` rewritten around the installer
  (gate + `install` + `install_post_commit_hook`); `tests/test_livingdocs_watch.py`
  rewritten around `run_once` gating + `derive_project_kb`; the
  `watch_interval_seconds` assertion dropped from `tests/test_livingdocs_config.py`.

`drift.py` is unchanged (still used by `run_once` and the statusline). The historical
plan `docs/plans/2026-06-03-living-docs.md` is left as-is (record of what was built).

## Verification

`pytest tests/hooks/ tests/ -k "livingdocs or auto_capture or watch or config or drift"`
→ 58 passed.
