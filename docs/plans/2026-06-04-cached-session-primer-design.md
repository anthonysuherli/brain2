# Cached broad session primer — preamble injection v2

**Date:** 2026-06-04
**Status:** Design approved; ready for implementation plan.
**Author:** Anthony Suherli (with Claude)
**Supersedes the per-turn recompute behavior in:** `docs/plans/2026-06-04-preamble-inject-hook-design.md`

## Goal

Make the `UserPromptSubmit` preamble injection **build once per session and reuse from
cache**, instead of re-grounding (and cold-importing `br8n`) on every turn. On a
session's first prompt for a given `(project, kb)`, build a rich, broad **session
primer** and cache it as a stdlib-readable file; every later turn reads the file (no
engine import) and injects the primer verbatim. A capture during the session clears
the cache so the next turn rebuilds.

This keeps "every answer is grounded" while collapsing the per-turn cost from ~1.3–1.6s
(cold import + embed, every turn) to ~10–50ms (stdlib file read) after turn 1.

## Why this shape (decisions already made)

- **Broad primer, reused verbatim** (not query-specific per turn): the cached blob is
  mostly query-independent orientation (synopsis + recent snapshots) seeded once by the
  first prompt's deep bands. Trades per-turn query-specificity for speed + always-on
  context.
- **Per session, refreshed on capture:** cache keyed by `(session_id, project, kb)`;
  a capture invalidates it; a new session rebuilds.
- **Cache hits must not import the heavy engine.** The real per-turn cost is the fresh
  process cold-importing `br8n.store`/`br8n.agent.preamble` (~0.9s, measured). The
  cache is therefore a **plain JSON file** read with stdlib only. Measured: `br8n/__init__.py`
  is empty and bare `import br8n` is ~0.001s, so importing a **pure-stdlib**
  `br8n.preamble_cache` submodule on the hit path stays ~10–50ms.

## Non-goals

- Not query-specific re-grounding per turn (that was v1; this supersedes it).
- No cross-repo activity in the primer (it's noise for grounding one repo; lives in
  `/br8n:activity`).
- No TTL-based invalidation (chosen: session scope + capture). A light age-based
  **prune** of the cache dir is housekeeping, not semantic invalidation.
- No new storage table — cache is files under `~/.br8n/`.

## Architecture

```
UserPromptSubmit {session_id, cwd, prompt}
   gate (BR8N_PREAMBLE_INJECT != "0")
   derive_target(cwd) → (project, kb)            # basename(toplevel), git branch
   cached = preamble_cache.read(session_id, project, kb)    # stdlib, ~10-50ms
   ├─ HIT  → emit hookSpecificOutput(additionalContext=cached); return
   └─ MISS → primer = asyncio.run(build_session_primer(project, kb, prompt))  # heavy import, once
             primer is None  → suppress (empty KB / error)
             else            → preamble_cache.write(session_id, project, kb, primer)
                               emit hookSpecificOutput(additionalContext=primer)

/v1/capture | br8n_capture ──► capture/service.py::persist_snapshot(ctx, snap)
                                   └─ preamble_cache.invalidate(basename(snap.project_path), snap.branch)  # best-effort
```

## Components

### 1. `backend/br8n/preamble_cache.py` (new — pure stdlib)
Imports only `os`, `json`, `hashlib`, `pathlib`, `time` (NO other `br8n` imports, so
the hook can import it cheaply). Cache dir via `_dir()` = `os.environ.get(
"BR8N_PREAMBLE_CACHE_DIR")` else `~/.br8n/preamble-cache/` (the env override exists
for hermetic tests; production uses `~/.br8n/` like the journal dir).

- `cache_key(project, kb) -> str` — `hashlib.sha256(f"{project}\\0{kb}".encode()).hexdigest()[:16]`.
- `_path(session_id, project, kb) -> Path` — `<dir>/{cache_key}.{slug(session_id)}.json`.
- `read(session_id, project, kb) -> str | None` — load the file's `primer` string, or
  `None` if missing/unreadable/malformed. Never raises.
- `write(session_id, project, kb, primer) -> None` — `mkdir(parents, exist_ok)`, write
  `{"built_at": <iso>, "primer": primer}`, then best-effort `prune()`. Never raises.
- `invalidate(project, kb) -> None` — unlink every `<dir>/{cache_key}.*.json` (all
  sessions for this repo+branch). Never raises.
- `prune(max_age_hours=24) -> None` — best-effort unlink of files older than the cutoff
  (keeps the dir bounded; not semantic invalidation). Never raises.

`built_at` is informational/prune-only; `read` does NOT TTL-check (session scope: while
the file exists for this session it's a hit; capture deletes it).

### 2. `backend/br8n/agent/session_primer.py` (new)
`async def build_session_primer(project, kb, query) -> str | None`:
- `res = await resume_preamble(project, kb, query, depth="deep")` (reuses the v1 core;
  `create=False` default — a read never creates a KB; may raise, caller catches).
- `snaps = res.store.list_findings(res.ctx.kb_id, category="snapshot", limit=3)["findings"]`.
- `has_orientation = ("<synopsis>" in res.preamble) or ("<finding " in res.preamble) or bool(snaps)`.
  `render_preamble` emits `<synopsis>` only when the synopsis is non-empty and `<finding `
  only when bands are admitted, so these substring checks are reliable against its
  contract. If `not has_orientation` → `return None` (truly empty KB → suppress).
- Render a compact `<recent-snapshots>` block from the snapshots' `title` (one line each,
  newest first), and return the **`additionalContext` payload** = `res.preamble` followed
  by the `<recent-snapshots>` block (a single composed string; `additionalContext` is
  free-form text, no single-root requirement). Bounded by the existing
  `preamble_char_budget` for the preamble part plus the small fixed snapshot block.

### 3. `hooks/preamble-inject.py` (modify)
Keep `derive_target` and `main`'s gate/stdin handling. Change the body:
- After `derive_target`, read `session_id = ctx.get("session_id") or ""`.
- `cached = _cache.read(session_id, project, kb)` where `_cache` is imported lazily
  (`from br8n import preamble_cache as _cache`) inside a `try/except` → on any import
  error, treat as a miss and continue (fail-silent).
- HIT (`cached` truthy) → `print(_inject(cached))`; return.
- MISS → `primer = _build(project, kb, prompt)` (the renamed `_fetch`: imports
  `br8n.agent.session_primer.build_session_primer`, `asyncio.run`s it, returns the
  string or `None` on any error). `None` → return (suppress). Else
  `_cache.write(session_id, project, kb, primer)` (best-effort) and `print(_inject(primer))`.
- `_inject(payload) -> str` = `json.dumps({"hookSpecificOutput": {"hookEventName":
  "UserPromptSubmit", "additionalContext": payload}})`. (Replaces v1 `decide` — the
  primer already encodes its own emptiness via `build_session_primer` returning `None`,
  so the hook no longer branches on a coverage string.)

### 4. `backend/br8n/capture/service.py::persist_snapshot` (modify)
After the successful `insert_findings` + `schedule_rebuild`, best-effort:
```python
try:
    from br8n import preamble_cache
    import os
    preamble_cache.invalidate(os.path.basename(snap.project_path.rstrip("/")), snap.branch or "")
except Exception:
    pass  # cache invalidation is best-effort; never break a capture
```
`snap.project_path` basename + `snap.branch` match the hook's `(project, kb)` derivation
in the common case (capture from the same repo). A mismatch just means the primer
persists until session end — acceptable degradation, never an error.

## Data flow

1. First prompt of a session in repo R / branch B → hook miss → `build_session_primer`
   imports the engine (~1.5s, once), composes synopsis + deep first-prompt bands +
   recent snapshots → cached to `~/.br8n/preamble-cache/{key}.{session}.json` → injected.
2. Every later prompt that session → hook reads the file (stdlib, ~10–50ms) → injects the
   same primer verbatim.
3. A capture (`/br8n:capture`, `/v1/capture`, MCP) → `persist_snapshot` → `invalidate(R,B)`
   deletes the cache file → next prompt rebuilds with the new snapshot.
4. New session → new `session_id` → miss → rebuild.

## Error handling — fail-silent, non-blocking (invariants)

Unchanged philosophy; every path suppresses (emit nothing, exit 0):
- `BR8N_PREAMBLE_INJECT=0`; not a git repo; malformed / non-object stdin (the v1 guards stay).
- Cache read error / missing file → treat as miss.
- `build_session_primer` raises (engine unimportable, unknown KB, embed/store error) → suppress.
- `build_session_primer` returns `None` (empty KB) → suppress, no cache write.
- Cache `write` / `invalidate` / `prune` errors → swallowed (best-effort); injection/
  capture still proceed.

## Latency

- **Cache hit** (the common case): `import br8n.preamble_cache` (~0.01–0.05s, empty
  `__init__` + stdlib module) + one file read + `print`. ~10–50ms.
- **Cache miss** (first turn per session, and the turn after a capture): the full
  ~1.3–1.6s build, paid once. Then hits until the next capture / new session.
- Net: a session of N turns pays ~1.5s once + ~(N−1)×~30ms, vs v1's N×~1.5s.

## Testing

- **`preamble_cache.py`** (`backend/tests/test_preamble_cache.py`): write→read roundtrip
  returns the primer; read of a missing file → `None`; `invalidate(project, kb)` removes
  the file for that repo+branch across sessions (create two session files, invalidate,
  assert both gone); a malformed JSON file → `read` returns `None` (no raise); `prune`
  removes an old file and keeps a fresh one. All hermetic via
  `monkeypatch.setenv("BR8N_PREAMBLE_CACHE_DIR", str(tmp_path))`.
- **`build_session_primer`** (`backend/tests/test_session_primer.py`): against a seeded
  local store, the primer string contains the synopsis and a recent-snapshot title;
  an empty/unknown KB → `None`. (Reuse the `local_engine`-style fixture that seeds
  findings without a live embedding API, as `test_engine_local.py` does.)
- **Hook** (`backend/tests/hooks/test_preamble_inject_hook.py`, rewrite the injection
  tests): cache HIT path injects the cached payload **without** calling `_build` (patch
  `_cache.read` to return a string, patch `_build` and assert not called); MISS path
  calls `_build`, writes the cache (patch `_cache.write`, assert called), and injects;
  `_build` `None` → silent and no `_cache.write`. The existing gate / non-git /
  malformed-stdin / non-object-stdin / `derive_target` suppress tests stay as-is. **The
  v1 `test_decide_*` and the coverage-based `test_main_silent_on_gap` tests are removed**
  — v2 has no per-turn coverage suppression in the hook; primer emptiness is decided in
  `build_session_primer` and covered by `test_session_primer.py`.
- **Capture invalidation** (`backend/tests/` capture test): after `persist_snapshot`,
  the matching cache file is gone (seed a cache file, persist a snapshot for that
  repo+branch, assert the file was unlinked). Best-effort: a cache error must not fail
  the capture.

## Config / kill switch

- `BR8N_PREAMBLE_INJECT=0` disables injection (unchanged).
- Cache dir `~/.br8n/preamble-cache/`; self-pruning (24h), self-healing (a corrupt
  file reads as a miss and is overwritten on the next build).

## Files

- NEW `backend/br8n/preamble_cache.py` — pure-stdlib cache (read/write/invalidate/prune).
- NEW `backend/br8n/agent/session_primer.py` — `build_session_primer` (reuses `resume_preamble`).
- MOD `hooks/preamble-inject.py` — cache layer; `_fetch`→`_build` (broad primer); `decide`→`_inject`.
- MOD `backend/br8n/capture/service.py` — best-effort `invalidate` after persist.
- NEW `backend/tests/test_preamble_cache.py`, `backend/tests/test_session_primer.py`.
- MOD `backend/tests/hooks/test_preamble_inject_hook.py` — cache hit/miss tests.
- MOD a capture test for the invalidation hook.
