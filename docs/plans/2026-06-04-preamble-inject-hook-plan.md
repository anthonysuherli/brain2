# Always-On Preamble Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject the current repo+branch KB's query-aware `<preamble>` silently before every Claude turn, via a `UserPromptSubmit` hook.

**Architecture:** A new `UserPromptSubmit` hook (`hooks/preamble-inject.py`) imports `br8n` in-process (mirroring `first-run-init.py`), derives `project`=toplevel basename / `kb`=git branch, and calls a newly-factored shared core `resume_preamble` (the resolve+store+select trio extracted from `br8n_resume` and `/v1/resume`). On `rich`/`sparse` coverage it prints `hookSpecificOutput.additionalContext` (silent context injection); on `gap`/empty/any error it emits nothing. Fail-silent and non-blocking throughout.

**Tech Stack:** Python 3.11, FastMCP, FastAPI, SQLite + sqlite-vec (local tier), pytest (asyncio auto-mode), Claude Code plugin hooks (`hooks/hooks.json`).

**Spec:** `docs/plans/2026-06-04-preamble-inject-hook-design.md`

---

## File Structure

- **Create** `backend/br8n/agent/resume.py` — shared `resume_preamble` core + `ResumeResult` dataclass.
- **Create** `backend/tests/test_resume_core.py` — wiring test for `resume_preamble` (mocked, no store/embeddings).
- **Modify** `backend/br8n/interfaces/mcp/server.py:298-314` — `br8n_resume` uses `resume_preamble`.
- **Modify** `backend/br8n/api/resume.py:82-85` — `/v1/resume` uses `resume_preamble`; drop now-unused imports.
- **Create** `hooks/preamble-inject.py` — the UserPromptSubmit hook (`derive_target` / `_fetch` / `decide` / `main`).
- **Create** `backend/tests/hooks/test_preamble_inject_hook.py` — hook logic tests (mock `_fetch`).
- **Modify** `hooks/hooks.json` — add the `UserPromptSubmit` block + update `description`.

All commands run from `backend/` unless noted. Use the repo venv: `./.venv/bin/python -m pytest …` (or `uv run pytest …`).

---

## Task 1: Shared `resume_preamble` core

**Files:**
- Create: `backend/br8n/agent/resume.py`
- Test: `backend/tests/test_resume_core.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_resume_core.py` (async style matches `tests/test_engine_local.py` — no explicit marker; the repo runs pytest-asyncio in auto mode):

```python
"""Wiring test for br8n.agent.resume.resume_preamble — mocked, no store/embeddings."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def test_resume_preamble_wires_resolve_store_and_select():
    from br8n.agent.resume import ResumeResult, resume_preamble

    fake_ctx = MagicMock(access_token="tok", org_id="org1", kb_id="kb1")
    fake_store = MagicMock()

    with (
        patch("br8n.interfaces.mcp.tenancy.resolve_tenant", return_value=fake_ctx) as m_rt,
        patch("br8n.store.get_store", return_value=fake_store) as m_gs,
        patch(
            "br8n.agent.resume.select_preamble",
            new=AsyncMock(return_value=("<preamble/>", "rich")),
        ) as m_sp,
    ):
        res = await resume_preamble("proj", "dev", "my query", depth="deep")

    assert isinstance(res, ResumeResult)
    assert res.preamble == "<preamble/>"
    assert res.coverage == "rich"
    assert res.ctx is fake_ctx
    assert res.store is fake_store
    m_rt.assert_called_once_with("proj", "dev", create=False, principal=None)
    m_gs.assert_called_once_with("tok", org_id="org1")
    m_sp.assert_awaited_once_with("my query", store=fake_store, kb_id="kb1", depth="deep")


async def test_resume_preamble_propagates_not_found():
    from br8n.agent.resume import resume_preamble

    with patch(
        "br8n.interfaces.mcp.tenancy.resolve_tenant",
        side_effect=RuntimeError("kb dev not found"),
    ):
        with pytest.raises(RuntimeError, match="not found"):
            await resume_preamble("proj", "dev", "q")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_resume_core.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'br8n.agent.resume'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/br8n/agent/resume.py`:

```python
"""Shared resume core — resolve the tenant, get the store, select the preamble.

    resolve_tenant(create=…) ─► get_store ─► select_preamble ─► ResumeResult

Factored out of the call sites that tap a KB the same way (``interfaces/mcp/server.py::
br8n_resume``, ``api/resume.py::resume``, and the ``hooks/preamble-inject.py``
UserPromptSubmit hook) so the resolve+select trio can't drift. Returns the resolved
``ctx``/``store`` alongside the preamble so callers needing them for follow-on work
(``record_access``, snapshot counts, JSON assembly) don't re-resolve.

May raise — ``resolve_tenant(create=False)`` raises on an unknown project/kb. Callers
that must stay silent (the hook) wrap the call in try/except.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from br8n.agent.preamble import Coverage, Depth, select_preamble

if TYPE_CHECKING:
    from br8n.agent.state import Principal, TenantContext
    from br8n.store import Store


@dataclass
class ResumeResult:
    ctx: "TenantContext"
    store: "Store"
    preamble: str
    coverage: Coverage


async def resume_preamble(
    project: str,
    kb: str,
    query: str | None,
    *,
    depth: Depth = "normal",
    principal: "Principal | None" = None,
    create: bool = False,
) -> ResumeResult:
    """Resolve the KB and return its query-aware preamble + coverage.

    ``create=False`` by default (a read): an unknown project/kb raises rather than
    being created. ``principal`` threads the per-request cloud identity; omit it for
    the local tier / configured-MCP-user path.
    """
    # Lazy imports: keep this module free of import cycles (tenancy imports agent.state;
    # store is heavy). Mirrors the lazy-import idiom in interfaces/mcp/tenancy.py.
    from br8n.interfaces.mcp.tenancy import resolve_tenant
    from br8n.store import get_store

    ctx = resolve_tenant(project, kb, create=create, principal=principal)
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    preamble, coverage = await select_preamble(query, store=store, kb_id=ctx.kb_id, depth=depth)
    return ResumeResult(ctx=ctx, store=store, preamble=preamble, coverage=coverage)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_resume_core.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint**

Run: `./.venv/bin/ruff check br8n/agent/resume.py tests/test_resume_core.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/br8n/agent/resume.py backend/tests/test_resume_core.py
git commit -m "feat(agent): shared resume_preamble core (resolve+store+select)"
```

---

## Task 2: Route `br8n_resume` and `/v1/resume` through the core

**Files:**
- Modify: `backend/br8n/interfaces/mcp/server.py` (imports + `br8n_resume` body, ~L298-314)
- Modify: `backend/br8n/api/resume.py` (imports + `resume` body, ~L82-85)

- [ ] **Step 1: Refactor `br8n_resume` in `server.py`**

Add the import near the other `from br8n.agent...` imports (top of `server.py`, by the `from br8n.agent.preamble import select_preamble` line):

```python
from br8n.agent.resume import resume_preamble
```

Replace the body of `br8n_resume` (currently L298-307, the `ctx =`/`store =`/`select_preamble`/`record_access` block) so it reads:

```python
    res = await resume_preamble(project, kb, query, depth=depth)
    await res.store.record_access(
        org_id=res.ctx.org_id,
        kb_id=res.ctx.kb_id,
        surface="mcp",
        targets=PREAMBLE_TARGETS,
        query_text=query,
    )
    return {
        "banner": BR8N_BANNER,
        "preamble": res.preamble,
        "coverage": res.coverage,
        "project": project,
        "kb": kb,
    }
```

> Leave every other `resolve_tenant(...)` / `get_store(...)` call in `server.py` untouched — they're used by the other tools. Do NOT remove those imports.

- [ ] **Step 2: Refactor `resume` in `api/resume.py`**

Add near the existing `from br8n.agent.preamble import select_preamble` import:

```python
from br8n.agent.resume import resume_preamble
```

Replace L82-85 (the `ctx =`/`store =`/`select_preamble` block) with:

```python
    res = await resume_preamble(project, kb, query, principal=principal)
    ctx, store, preamble_xml, coverage = res.ctx, res.store, res.preamble, res.coverage
```

Everything below (`snapshot_count = store.list_findings(ctx.kb_id, …)`, `rollup`, `_assemble_json`, `_render_card`) is unchanged — it consumes `ctx`, `store`, `preamble_xml`, `coverage` exactly as before.

- [ ] **Step 3: Drop now-unused imports in `api/resume.py`**

Run: `./.venv/bin/ruff check br8n/api/resume.py`
If ruff reports `resolve_tenant`, `get_store`, or `select_preamble` as unused (F401), remove those import lines. (Keep any that other functions in the file still use — check with `grep -n "resolve_tenant\|get_store\|select_preamble" br8n/api/resume.py`.)
Expected after fix: no errors.

- [ ] **Step 4: Run regression (both call sites)**

Run: `./.venv/bin/python -m pytest tests/test_api_read_surfaces.py tests/test_engine_local.py -v`
Expected: PASS — including `test_resume_json_format_returns_structured_card`, `test_resume_default_format_is_html`, `test_select_preamble_reflects_snapshot`.

- [ ] **Step 5: Import-smoke the MCP server module**

Run: `./.venv/bin/python -c "import br8n.interfaces.mcp.server; import br8n.api.resume; print('ok')"`
Expected: `ok` (no ImportError / circular-import error).

- [ ] **Step 6: Commit**

```bash
git add backend/br8n/interfaces/mcp/server.py backend/br8n/api/resume.py
git commit -m "refactor(resume): route br8n_resume + /v1/resume through resume_preamble"
```

---

## Task 3: The `UserPromptSubmit` hook

**Files:**
- Create: `hooks/preamble-inject.py`
- Test: `backend/tests/hooks/test_preamble_inject_hook.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/hooks/test_preamble_inject_hook.py` (loads the hook by file path, exactly like `test_first_run_guard.py`):

```python
"""Tests for hooks/preamble-inject.py — the UserPromptSubmit preamble-injection hook.

Loads the hook module by file path (it lives outside backend/) and patches its
functions so no real store/embeddings are touched.
"""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_HOOK_PATH = Path(__file__).parents[3] / "hooks" / "preamble-inject.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("preamble_inject", _HOOK_PATH)
    assert spec is not None and spec.loader is not None, f"Cannot load {_HOOK_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


_hook = _load_hook()
derive_target = _hook.derive_target
decide = _hook.decide


# --- decide ---------------------------------------------------------------

def test_decide_injects_for_rich():
    out = decide("rich", "<preamble>x</preamble>")
    assert out is not None
    parsed = json.loads(out)
    assert parsed["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert parsed["hookSpecificOutput"]["additionalContext"] == "<preamble>x</preamble>"


def test_decide_injects_for_sparse():
    assert decide("sparse", "<preamble>x</preamble>") is not None


def test_decide_suppresses_on_gap():
    assert decide("gap", "<preamble>x</preamble>") is None


def test_decide_suppresses_on_empty_preamble():
    assert decide("rich", "") is None
    assert decide("rich", "   ") is None


# --- derive_target --------------------------------------------------------

def test_derive_target_none_for_non_git(tmp_path):
    assert derive_target(str(tmp_path)) is None


def test_derive_target_returns_basename_and_branch(tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "checkout", "-b", "feature/x"], cwd=str(tmp_path), check=True, capture_output=True
    )
    target = derive_target(str(tmp_path))
    assert target is not None
    project, kb = target
    assert project == tmp_path.name
    assert kb == "feature/x"


# --- main -----------------------------------------------------------------

def _run_main_with_stdin(payload: dict):
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        _hook.main()
    finally:
        sys.stdin = sys.__stdin__


def test_main_injects_when_rich(capsys, tmp_path):
    with (
        patch.object(_hook, "derive_target", return_value=("repo", "dev")),
        patch.object(_hook, "_fetch", return_value=("<preamble>p</preamble>", "rich")),
    ):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "how does capture work"})
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["additionalContext"] == "<preamble>p</preamble>"


def test_main_silent_on_gap(capsys, tmp_path):
    with (
        patch.object(_hook, "derive_target", return_value=("repo", "dev")),
        patch.object(_hook, "_fetch", return_value=("<preamble/>", "gap")),
    ):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi"})
    assert capsys.readouterr().out == ""


def test_main_silent_when_fetch_fails(capsys, tmp_path):
    with (
        patch.object(_hook, "derive_target", return_value=("repo", "dev")),
        patch.object(_hook, "_fetch", return_value=None),
    ):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi"})
    assert capsys.readouterr().out == ""


def test_main_silent_when_not_git(capsys, tmp_path):
    with patch.object(_hook, "derive_target", return_value=None):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi"})
    assert capsys.readouterr().out == ""


def test_main_silent_when_gate_disabled(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_PREAMBLE_INJECT", "0")
    with patch.object(_hook, "derive_target", return_value=("repo", "dev")) as m:
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi"})
    assert capsys.readouterr().out == ""
    m.assert_not_called()


def test_main_handles_malformed_stdin(capsys):
    sys.stdin = io.StringIO("not json{{{")
    try:
        _hook.main()
    finally:
        sys.stdin = sys.__stdin__
    assert capsys.readouterr().out == ""


def test_fetch_returns_none_on_error():
    """_fetch swallows a failed engine call and returns None (suppress)."""
    with patch("br8n.agent.resume.resume_preamble", side_effect=RuntimeError("kb dev not found")):
        assert _hook._fetch("repo", "dev", "q") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/hooks/test_preamble_inject_hook.py -v`
Expected: FAIL — `Cannot load …/hooks/preamble-inject.py` (file doesn't exist yet).

- [ ] **Step 3: Write the hook**

Create `hooks/preamble-inject.py`:

```python
"""br8n UserPromptSubmit hook — always-on preamble injection.

    python hooks/preamble-inject.py

Before each user turn, taps the current repo+branch KB on the user's prompt and
injects the query-aware <preamble> (synopsis spine + similarity-banded findings) as
additionalContext, so Claude answers grounded — no skill invocation, no visible tool
call. Imports br8n in-process (mirrors first-run-init.py) and runs the shared
resume_preamble core.

Design goals
------------
* **Silent.** Injects via hookSpecificOutput.additionalContext; nothing is printed to
  the user, no tool call.
* **Non-blocking, fail-silent.** Not a git repo, no KB for this branch, coverage=gap,
  br8n unimportable, or any error → emit nothing, exit 0. Never crashes the turn.
* **Importable for testing.** Logic lives in derive_target / _fetch / decide; main()
  is thin glue. Tests patch _fetch (no store/embeddings needed).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def derive_target(cwd: str) -> tuple[str, str] | None:
    """Return (project, kb) = (toplevel basename, current branch), or None if not git.

    Matches skills/_shared/preamble-first.md and the capture path exactly: project is
    the repo folder name, kb is the git branch (NOT the hardcoded 'main' that
    first-run-init's derive_project_kb returns)."""
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if top.returncode != 0:
            return None
        project = os.path.basename(top.stdout.strip())
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if branch.returncode != 0:
            return None
        kb = branch.stdout.strip()
        if not project or not kb:
            return None
        return project, kb
    except Exception:  # noqa: BLE001 — subprocess/timeout failure → no target
        return None


def _fetch(project: str, kb: str, query: str) -> tuple[str, str] | None:
    """Import br8n in-process and return (preamble_xml, coverage), or None on any error.

    Mirrors first-run-init.check_kb_exists: the hook runs where br8n is importable;
    an unknown KB (create=False raises 'not found'), an import error, or any backend
    error degrades to None (suppress)."""
    try:
        import asyncio

        from br8n.agent.resume import resume_preamble

        res = asyncio.run(resume_preamble(project, kb, query=query, create=False))
        return res.preamble, res.coverage
    except Exception:  # noqa: BLE001 — fail-silent: never break the turn
        return None


def decide(coverage: str, preamble_xml: str) -> str | None:
    """Return the JSON to print to inject the preamble, or None to suppress.

    Suppress on gap or an empty preamble; otherwise wrap the XML in the
    UserPromptSubmit additionalContext shape (silent context injection)."""
    if coverage == "gap" or not preamble_xml or not preamble_xml.strip():
        return None
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": preamble_xml,
            }
        }
    )


def main() -> None:
    """UserPromptSubmit entry point. Reads {prompt, cwd} from stdin; injects or stays silent."""
    if os.getenv("BR8N_PREAMBLE_INJECT", "1") == "0":
        return
    try:
        raw = sys.stdin.read()
        ctx = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 — malformed stdin → silent
        return

    cwd = ctx.get("cwd") or (ctx.get("session") or {}).get("cwd") or os.getcwd()
    prompt = ctx.get("prompt") or ""

    target = derive_target(cwd)
    if target is None:
        return
    project, kb = target

    fetched = _fetch(project, kb, prompt)
    if fetched is None:
        return
    preamble, coverage = fetched

    out = decide(coverage, preamble)
    if out:
        print(out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/hooks/test_preamble_inject_hook.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Lint**

Run: `./.venv/bin/ruff check tests/hooks/test_preamble_inject_hook.py && ./.venv/bin/ruff check ../hooks/preamble-inject.py`
Expected: no errors. (If `hooks/` is outside ruff's configured paths, lint just the test file; the hook mirrors existing `hooks/*.py` style.)

- [ ] **Step 6: Commit**

```bash
git add hooks/preamble-inject.py backend/tests/hooks/test_preamble_inject_hook.py
git commit -m "feat(hooks): UserPromptSubmit preamble-injection hook (silent, fail-safe)"
```

---

## Task 4: Wire the hook into `hooks/hooks.json`

**Files:**
- Modify: `hooks/hooks.json`

- [ ] **Step 1: Add the `UserPromptSubmit` block**

In `hooks/hooks.json`, add this block to the `"hooks"` object (alongside `SessionStart` / `SessionEnd` / `Stop`):

```json
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/preamble-inject.py",
            "timeout": 8
          }
        ]
      }
    ]
```

And update the top-level `"description"` string to append: ` UserPromptSubmit injects the current repo+branch KB preamble before each turn (silent, fail-safe).`

- [ ] **Step 2: Validate the JSON**

Run: `python -c "import json; json.load(open('hooks/hooks.json')); print('valid json')"` (from repo root)
Expected: `valid json`.

- [ ] **Step 3: Full backend test sweep**

Run (from `backend/`): `./.venv/bin/python -m pytest tests/test_resume_core.py tests/hooks/test_preamble_inject_hook.py tests/test_api_read_surfaces.py tests/test_engine_local.py -q`
Expected: all PASS.

- [ ] **Step 4: Manual smoke (real engine, no harness)**

Simulate a UserPromptSubmit payload for a repo+branch that has captures (e.g. `br8n`/`dev`, which has snapshots). From repo root:

```bash
echo '{"cwd":"'"$(pwd)"'","prompt":"how does capture become a finding"}' | python hooks/preamble-inject.py
```

Expected: a single JSON line containing `"hookSpecificOutput"` with a `<preamble>…` `additionalContext` **if** coverage is rich/sparse for that query; **empty output** if the query bands as gap. Either is a correct pass (no traceback, exit 0). Verify a gap case stays silent:

```bash
echo '{"cwd":"'"$(pwd)"'","prompt":"zzqqxx nonsense token unlikely to match"}' | python hooks/preamble-inject.py
```

Expected: empty output, exit 0.

And the kill switch:

```bash
echo '{"cwd":"'"$(pwd)"'","prompt":"anything"}' | BR8N_PREAMBLE_INJECT=0 python hooks/preamble-inject.py
```

Expected: empty output, exit 0.

> Note: `python` here must be the interpreter where `br8n` is importable (the backend venv), same as the other hooks. If it isn't, `_fetch` returns `None` → empty output (fail-silent) — which is the designed degradation, not a bug.

- [ ] **Step 5: Commit**

```bash
git add hooks/hooks.json
git commit -m "feat(hooks): register UserPromptSubmit preamble-inject in hooks.json"
```

- [ ] **Step 6 (optional): Live verification in a fresh session**

Reload the plugin / restart the Claude Code session so the new hook is picked up, then ask a question in a captured repo+branch and confirm the answer is grounded (and that no extra tool call or visible card appears each turn). If the per-turn latency is noticeable, that's the cue to build **Option C** (warm sidecar) from the spec — not part of this plan.

---

## Self-Review

**Spec coverage:**
- Silent injection via `hookSpecificOutput.additionalContext` → Task 3 `decide`. ✓
- Every-turn `UserPromptSubmit` hook → Task 4. ✓
- Query-aware (`query=prompt`) → Task 3 `main`/`_fetch`. ✓
- `kb`=branch (not `derive_project_kb`'s "main") → Task 3 `derive_target` + test. ✓
- Fail-silent/self-gating (gate, non-git, unknown KB, gap, import/backend error) → Task 3 tests `test_main_silent_*`, `test_fetch_returns_none_on_error`. ✓
- In-process import (no subprocess/entrypoint) → Task 3 `_fetch`. ✓
- Shared `resume_preamble` core, all three call sites → Tasks 1-2. ✓
- Plugin `hooks.json` home + `BR8N_PREAMBLE_INJECT` kill switch → Tasks 3-4 + `test_main_silent_when_gate_disabled`. ✓
- Latency note / Option C upgrade → spec only (out of scope for this plan), surfaced in Task 4 Step 6. ✓

**Placeholder scan:** none — every code step has complete code; every command has expected output.

**Type/name consistency:** `resume_preamble(project, kb, query, *, depth, principal, create)` and `ResumeResult(ctx, store, preamble, coverage)` are used identically in Tasks 1-3. Hook functions `derive_target` / `_fetch` / `decide` / `main` are referenced consistently across the hook and its tests. `BR8N_PREAMBLE_INJECT` spelled identically in hook + test. `hookSpecificOutput`/`hookEventName`/`additionalContext` keys match between `decide` and its assertions.
