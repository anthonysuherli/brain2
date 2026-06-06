# Always-on preamble injection — `UserPromptSubmit` hook

**Date:** 2026-06-04
**Status:** Design approved; ready for implementation plan.
**Author:** Anthony Suherli (with Claude)

## Goal

Make br8n ground **every** answer in the session KB automatically. Before each
user turn, fetch the query-aware `<preamble>` (synopsis spine + similarity-banded
findings) for the current repo+branch and inject it silently into Claude's context,
so the answer is grounded without the user invoking a skill or Claude making a
visible tool call.

This generalizes the existing `skills/_shared/preamble-first.md` convention — today
opt-in per skill — into an always-on, every-turn default.

## Non-goals

- Not a visible resume card each turn (that's `/br8n:pickup`). Injection is silent.
- Not a replacement for the skills' explicit resume-first step; this is a baseline
  that runs underneath them.
- Not a new retrieval path: it reuses `select_preamble` unchanged.
- No cloud/multi-user concerns — the hook targets the local tier (single user,
  loopback). On a machine configured for cloud it still works through `get_store`,
  but the hook is designed and tested against local SQLite.

## Design philosophy alignment

br8n's rule is "non-blocking by default — never hijack the user's turn." That rule
targets br8n's **own background work** (seeding, distillation, KG population).
Grounding on the user's intent is a **direct response** to their turn, not background
work, so a synchronous preamble read is consistent with the philosophy. The cost is
real (~1.3–1.6s/turn, see Latency) and is bounded by the hook timeout and a
fail-silent contract, honoring "best-effort, fails silent."

## Architecture

A new hook on the one event that fires *before each answer*: **`UserPromptSubmit`**.

```
UserPromptSubmit {prompt, cwd}
        │
        ▼
hooks/preamble-inject.py            (python hook; imports br8n in-process — like first-run-init.py)
  ├─ gate: BR8N_PREAMBLE_INJECT != "0"
  ├─ derive_target(cwd):  git rev-parse --show-toplevel → basename = project
  │                       git rev-parse --abbrev-ref HEAD = kb (the BRANCH)   (None if not a git repo)
  ├─ asyncio.run(resume_preamble(project, kb, query=prompt, create=False))
  │      └─ resolve_tenant(create=False) → get_store → select_preamble  → (preamble_xml, coverage)
  │      (the whole call is wrapped in try/except in the hook → any error suppresses)
  └─ decide(coverage, preamble_xml):
        gap / empty / raised  → emit nothing, exit 0          (never blocks)
        rich / sparse         → print hookSpecificOutput JSON (silent inject)
        │
        ▼
harness injects <preamble> as additionalContext  →  Claude answers grounded
```

### Mechanism — in-process import (the rejected/deferred alternatives)

`first-run-init.py` already imports `br8n` in-process (`from br8n.interfaces.mcp.tenancy
import resolve_tenant; asyncio.run(...)`) and is shipping, working code — so hooks DO run
where `br8n` is importable. The preamble hook follows that exact pattern: import the
engine in-process and `asyncio.run` the shared core, wrapped in a fail-silent try/except
(on `ImportError` or any error → no injection). No subprocess, no venv-path resolution, no
separate entrypoint module. The per-turn cold-import cost is the same either way (each hook
run is a fresh process).

> **`kb` correction:** the hook must NOT reuse `derive_project_kb` — it hardcodes `kb="main"`,
> but real captures go to `kb=<git branch>` (e.g. `br8n · dev`, 18 snapshots). Tapping
> `"main"` would always miss. The hook derives `project = basename(toplevel)` and
> `kb = current branch`, matching `skills/_shared/preamble-first.md` and the capture path.

| Option | Mechanism | Latency/turn | Verdict |
|---|---|---|---|
| A | Emit a directive telling Claude to call `br8n_resume` | ~0.4s (warm MCP) | **Rejected** — produces a *visible* tool call every turn; not silent. |
| **B** | Hook imports `br8n` in-process → `resume_preamble` → inject XML | ~1.3–1.6s cold | **Chosen for v1** — simple, deterministic, truly silent; mirrors `first-run-init.py`. |
| C | SessionStart launches a warm preamble sidecar; hook talks to it over a socket | ~0.3s warm | **Deferred upgrade** — reuses the existing `auto-capture.py` "launch watcher on SessionStart" pattern; build only if B's per-turn tax proves annoying. |

## Components

### 1. `hooks/preamble-inject.py` (new) — the UserPromptSubmit hook
- A `python` hook that imports `br8n` in-process, mirroring `first-run-init.py`
  (`asyncio.run` + fail-silent on `ImportError`/any error).
- Reads stdin JSON `{prompt, cwd, ...}` (provided by the harness on UserPromptSubmit;
  also accepts the nested `session.cwd` shape like the other hooks).
- **Gate:** `os.getenv("BR8N_PREAMBLE_INJECT", "1") == "0"` → silent exit.
- **`derive_target(cwd) -> tuple[str, str] | None`** (new, in this hook): `project =
  basename(git rev-parse --show-toplevel)`, `kb = git rev-parse --abbrev-ref HEAD`;
  returns `None` if `cwd` is not a git repo. Matches `preamble-first.md` + the capture
  path exactly. (Does NOT use `derive_project_kb`, which hardcodes `kb="main"`.)
- Calls `asyncio.run(resume_preamble(project, kb, query=prompt, create=False))` inside
  a `try/except Exception` — any failure (engine import error, unknown KB raising
  "not found", embed/store error) → suppress, exit 0. The hook owns fail-silent; the
  core stays clean (it may raise, exactly like `br8n_resume`).
- **Decision** via `decide(coverage, preamble_xml) -> str | None`: returns `None`
  (suppress) for `coverage == "gap"` or empty preamble; otherwise returns the JSON
  string to print.
- **Output shape:** `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
  "additionalContext": "<preamble>…</preamble>"}}` — the UserPromptSubmit
  context-injection form, which adds to context silently (not shown to the user).
- **Pure, importable logic** for tests: `derive_target`, `decide`, and the gate/parse
  glue in `main()`, mirroring how `session-note.py` isolates `build_note_directive`.
  Tests mock `resume_preamble` (no store/embeddings needed), exactly as the
  `check_kb_exists` tests mock `resolve_tenant`.

### 2. `br8n/agent/resume.py` — shared resolution callable (new module, small refactor)
Today the three resolve lines are inlined in two places:
```python
ctx = resolve_tenant(project, kb, create=False)
store = get_store(ctx.access_token, org_id=ctx.org_id)
preamble, coverage = await select_preamble(query, store=store, kb_id=ctx.kb_id, depth=depth)
```
(`interfaces/mcp/server.py::br8n_resume` and `api/resume.py::resume`). The hook
entrypoint would be a third copy. Factor these three lines into one callable in a new
`br8n/agent/resume.py` — `async def resume_preamble(project, kb, query, *,
depth="normal", principal=None) -> tuple[str, Coverage]` — and have all three call
sites use it, so the hook and the MCP tool can't drift. It lives one layer **above**
`agent/preamble.py` (which stays pure: imports only `clients.embeddings` + `config`);
`resume.py` owns the `resolve_tenant` + `get_store` wrapper. (The MCP/API sites
additionally do `record_access`/banner formatting around the core; only the
resolve+select trio moves.)

### 3. `hooks/hooks.json` (edit)
Add a `UserPromptSubmit` matcher block alongside the existing `SessionStart` /
`SessionEnd` / `Stop` blocks:
```json
"UserPromptSubmit": [
  { "matcher": "*", "hooks": [
    { "type": "command",
      "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/preamble-inject.py",
      "timeout": 8 }
  ]}
]
```
Update the file-level `description` to mention the new hook.

## Data flow

1. User submits a prompt. Harness fires `UserPromptSubmit` with `{prompt, cwd}`.
2. Hook gates, `derive_target(cwd)` → `project`=toplevel basename / `kb`=branch.
3. Hook `asyncio.run(resume_preamble(project, kb, query=prompt, create=False))`,
   wrapped in `try/except` → on any error, suppress.
4. Core returns `(preamble_xml, coverage)`.
5. `decide(...)` suppresses on gap/empty; otherwise prints the `hookSpecificOutput`
   `additionalContext` JSON.
6. Harness injects the `<preamble>` into context; Claude answers grounded.

## Error handling — fail-silent, non-blocking (invariants)

The hook must **never** crash or block Claude Code. Every one of these → emit
nothing, exit 0:
- `BR8N_PREAMBLE_INJECT=0` (kill switch).
- Not a git repo (`derive_target` → `None`) / malformed stdin.
- KB does not exist for this repo+branch (`resolve_tenant(create=False)` raises
  "... not found"; caught by the hook's `try/except`).
- `coverage == "gap"` or empty preamble (nothing worth injecting).
- `br8n` not importable, embed/store error (caught by the hook's `try/except`).
- Hook exceeds the `hooks.json` `timeout` (the harness kills it; the turn proceeds
  ungrounded).

## Latency

- Measured cold import of the preamble path under the venv: **~0.9s** import
  (~1.0s process-real), before embed + vector search.
- Realistic per-turn cost: **~1.3–1.6s** (cold import + one embedding call + local
  vector search). Each hook run is a fresh process, so the cold import recurs every
  turn (in-process vs subprocess doesn't change this). Bounded by the `hooks.json`
  `timeout` (8s); on overrun the turn proceeds ungrounded.
- Upgrade path if this tax is felt: **Option C** (warm SessionStart sidecar over a
  unix socket, ~0.3s warm), reusing the `auto-capture.py` watcher lifecycle. Not built
  in v1 (YAGNI).

## Testing

Mirror `session-note.py` / `first-run-init.py`'s split — pure logic unit-tested,
the engine call mocked (no store/embeddings in hook tests):
- **Hook logic** (`backend/tests/hooks/test_preamble_inject_hook.py`, alongside
  `test_first_run_guard.py`, loaded by file path the same way): `decide("rich", xml)`
  and `decide("sparse", xml)` return the injection JSON; `decide("gap", …)` and
  `decide(_, "")` return `None`; `main()` prints `additionalContext` when
  `resume_preamble` is patched to return `("<preamble>…</preamble>", "rich")`, and is
  **silent** when it returns `(…, "gap")`, raises `RuntimeError("kb not found")`, or
  raises `ImportError`; the `BR8N_PREAMBLE_INJECT=0` gate and a non-git `derive_target`
  (`None`) both suppress; malformed stdin suppresses.
- **Shared `resume_preamble`** (`backend/tests/test_resume_core.py`): with
  `resolve_tenant`, `get_store`, and `select_preamble` patched, assert `resume_preamble`
  calls them in order with the right args (`create=False` passed through) and returns
  the `(preamble, coverage)` tuple `select_preamble` produced — a wiring test, no
  embeddings.
- **Regression**: the existing `br8n_resume` / `/v1/resume` tests still pass after
  both call sites are switched to `resume_preamble`.

## Config / kill switch

- `BR8N_PREAMBLE_INJECT` (default `"1"`): set `"0"` to disable injection globally.
- Lives in the plugin `hooks/hooks.json` (ships to every br8n plugin user;
  self-gates to a no-op in non-br8n repos).

## Files

- `hooks/preamble-inject.py` — new hook (python; imports `br8n` in-process).
- `hooks/hooks.json` — add `UserPromptSubmit` block + description.
- `backend/br8n/agent/resume.py` — new module: shared `resume_preamble` callable;
  update `interfaces/mcp/server.py::br8n_resume` and `api/resume.py::resume` to use it.
- `backend/tests/test_resume_core.py` — `resume_preamble` wiring test.
- `backend/tests/hooks/test_preamble_inject_hook.py` — hook decision-logic tests.
