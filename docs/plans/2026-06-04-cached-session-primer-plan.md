# Cached Session Primer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the injected preamble once per session and reuse it from a stdlib-readable cache, instead of cold-importing `br8n` and re-grounding every turn.

**Architecture:** A pure-stdlib `br8n.preamble_cache` (file cache under `~/.br8n/preamble-cache/`, keyed by `(session_id, project, kb)`) lets the `UserPromptSubmit` hook serve cache hits in ~10–50ms without importing the heavy engine. On a miss, `br8n.agent.session_primer.build_session_primer` (reusing the existing `resume_preamble` core, `depth="deep"`, plus recent snapshots) composes a broad primer, which is cached and injected. A capture invalidates the cache via `persist_snapshot`.

**Tech Stack:** Python 3.11, SQLite + sqlite-vec (local tier), pytest (asyncio auto-mode), Claude Code plugin hooks.

**Spec:** `docs/plans/2026-06-04-cached-session-primer-design.md`

---

## File Structure

- **Create** `backend/br8n/preamble_cache.py` — pure-stdlib file cache (read/write/invalidate/prune).
- **Create** `backend/tests/test_preamble_cache.py` — cache module tests.
- **Create** `backend/br8n/agent/session_primer.py` — `build_session_primer` (reuses `resume_preamble`).
- **Create** `backend/tests/test_session_primer.py` — primer builder + capture-invalidation tests.
- **Modify** `hooks/preamble-inject.py` — cache layer; `_fetch`→`_build` (broad primer); `decide`→`_inject`.
- **Rewrite** `backend/tests/hooks/test_preamble_inject_hook.py` — cache hit/miss tests (drop v1 coverage tests).
- **Modify** `backend/br8n/capture/service.py` — best-effort `invalidate` after persist.

Run pytest/ruff from `/Users/suherli/Repositories/br8n/backend` with `./.venv/bin/python` / `./.venv/bin/ruff`.

---

## Task 1: Pure-stdlib `preamble_cache`

**Files:**
- Create: `backend/br8n/preamble_cache.py`
- Test: `backend/tests/test_preamble_cache.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_preamble_cache.py`:

```python
"""Tests for br8n.preamble_cache — the stdlib file cache for the session primer."""
from __future__ import annotations

import os
import time

import pytest


@pytest.fixture(autouse=True)
def cache_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("BR8N_PREAMBLE_CACHE_DIR", str(tmp_path))
    return tmp_path


def test_write_read_roundtrip():
    from br8n import preamble_cache

    preamble_cache.write("sess1", "proj", "dev", "<preamble>hi</preamble>")
    assert preamble_cache.read("sess1", "proj", "dev") == "<preamble>hi</preamble>"


def test_read_missing_returns_none():
    from br8n import preamble_cache

    assert preamble_cache.read("nope", "proj", "dev") is None


def test_invalidate_removes_all_sessions():
    from br8n import preamble_cache

    preamble_cache.write("s1", "proj", "dev", "a")
    preamble_cache.write("s2", "proj", "dev", "b")
    preamble_cache.invalidate("proj", "dev")
    assert preamble_cache.read("s1", "proj", "dev") is None
    assert preamble_cache.read("s2", "proj", "dev") is None


def test_invalidate_scoped_to_project_kb():
    from br8n import preamble_cache

    preamble_cache.write("s1", "proj", "dev", "a")
    preamble_cache.write("s1", "other", "dev", "b")
    preamble_cache.invalidate("proj", "dev")
    assert preamble_cache.read("s1", "proj", "dev") is None
    assert preamble_cache.read("s1", "other", "dev") == "b"


def test_malformed_file_reads_as_none(cache_dir):
    from br8n import preamble_cache

    path = cache_dir / f"{preamble_cache.cache_key('proj', 'dev')}.s1.json"
    path.write_text("not json{{{")
    assert preamble_cache.read("s1", "proj", "dev") is None


def test_prune_removes_old_keeps_fresh(cache_dir):
    from br8n import preamble_cache

    preamble_cache.write("old", "proj", "dev", "x")
    old_file = next(cache_dir.glob("*.json"))
    stale = time.time() - 100 * 3600
    os.utime(old_file, (stale, stale))
    preamble_cache.write("fresh", "proj", "dev", "y")  # write() triggers prune()
    assert preamble_cache.read("old", "proj", "dev") is None
    assert preamble_cache.read("fresh", "proj", "dev") == "y"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_preamble_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'br8n.preamble_cache'`.

- [ ] **Step 3: Write the module**

Create `backend/br8n/preamble_cache.py`:

```python
"""Stdlib-only cache for the injected session preamble primer.

Keyed by (session_id, project, kb). Read on every UserPromptSubmit turn by
hooks/preamble-inject.py — so this module imports ONLY the standard library
(br8n/__init__.py is empty, so `import br8n.preamble_cache` stays ~ms and never
pulls the heavy engine). Written on a cache miss; invalidated by a capture.

Every function is best-effort and never raises: a corrupt/missing file reads as a
miss, write/invalidate/prune failures are swallowed. The cache never breaks a turn.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


def _dir() -> Path:
    override = os.environ.get("BR8N_PREAMBLE_CACHE_DIR")
    return Path(override) if override else Path.home() / ".br8n" / "preamble-cache"


def cache_key(project: str, kb: str) -> str:
    """Stable 16-hex key for a (project, kb) pair."""
    return hashlib.sha256(f"{project}\0{kb}".encode()).hexdigest()[:16]


def _slug(s: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in s) or "default"


def _path(session_id: str, project: str, kb: str) -> Path:
    return _dir() / f"{cache_key(project, kb)}.{_slug(session_id)}.json"


def read(session_id: str, project: str, kb: str) -> str | None:
    """Return the cached primer string, or None if missing/unreadable/malformed."""
    try:
        data = json.loads(_path(session_id, project, kb).read_text())
        primer = data.get("primer")
        return primer if isinstance(primer, str) and primer else None
    except Exception:  # noqa: BLE001 — any miss/corruption → cache miss
        return None


def write(session_id: str, project: str, kb: str, primer: str) -> None:
    """Best-effort write of the primer, then prune old files. Never raises."""
    try:
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        _path(session_id, project, kb).write_text(
            json.dumps({"built_at": time.time(), "primer": primer})
        )
        prune()
    except Exception:  # noqa: BLE001 — cache write is best-effort
        pass


def invalidate(project: str, kb: str) -> None:
    """Delete the cached primer for (project, kb) across all sessions. Never raises."""
    try:
        prefix = cache_key(project, kb)
        for f in _dir().glob(f"{prefix}.*.json"):
            try:
                f.unlink()
            except OSError:
                pass
    except Exception:  # noqa: BLE001 — best-effort
        pass


def prune(max_age_hours: float = 24.0) -> None:
    """Best-effort removal of cache files older than max_age_hours. Never raises."""
    try:
        cutoff = time.time() - max_age_hours * 3600
        for f in _dir().glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_preamble_cache.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Lint**

Run: `./.venv/bin/ruff check br8n/preamble_cache.py tests/test_preamble_cache.py`
Expected: no errors.

- [ ] **Step 6: Verify the import is cheap (the whole point)**

Run: `./.venv/bin/python -c "import time; t=time.time(); import br8n.preamble_cache; print('import_s', round(time.time()-t,3))"`
Expected: well under 0.2s (the module pulls no heavy deps).

- [ ] **Step 7: Commit**

```bash
git add backend/br8n/preamble_cache.py backend/tests/test_preamble_cache.py
git commit -m "feat(cache): pure-stdlib preamble_cache (read/write/invalidate/prune)"
```

---

## Task 2: `build_session_primer`

**Files:**
- Create: `backend/br8n/agent/session_primer.py`
- Test: `backend/tests/test_session_primer.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_session_primer.py` (the `local_engine` fixture mirrors `tests/test_engine_local.py` — fake embedder, local DB; it also pins the cache dir so the Task 4 capture-invalidation hook can't touch the real `~/.br8n`):

```python
"""Tests for build_session_primer (and the capture cache-invalidation hook)."""
from __future__ import annotations

import hashlib

import pytest

DIM = 1536


def _fake_vec(text):
    h = hashlib.sha256(text.encode()).digest()
    v = [0.0] * DIM
    for i in range(8):
        v[i] = (h[i] / 255.0) or 0.01
    return v


async def _fake_embed_batch(texts):
    return [_fake_vec(t) for t in texts]


async def _fake_embed_text(text):
    return _fake_vec(text)


@pytest.fixture
def local_engine(monkeypatch, tmp_path):
    import br8n.store as store_pkg

    monkeypatch.setenv("BR8N_BACKEND", "local")
    monkeypatch.setenv("BR8N_DB_PATH", str(tmp_path / "engine.db"))
    monkeypatch.setenv("BR8N_PREAMBLE_CACHE_DIR", str(tmp_path / "pcache"))
    store_pkg._local_stores.clear()

    import br8n.agent.preamble as preamble
    import br8n.capture.service as capture_service

    monkeypatch.setattr(capture_service, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(preamble, "embed_text", _fake_embed_text)
    yield store_pkg
    store_pkg._local_stores.clear()


def _snapshot(hypothesis):
    from br8n.capture.models import WorkspaceSnapshot

    return WorkspaceSnapshot(
        project_path="/tmp/proj",
        trigger="blur",
        captured_at="2026-05-29T12:00:00Z",
        branch="main",
        hypothesis=hypothesis,
    )


async def test_primer_includes_snapshot(local_engine):
    from br8n.agent.session_primer import build_session_primer
    from br8n.capture.service import persist_snapshot
    from br8n.interfaces.mcp.tenancy import resolve_tenant

    ctx = resolve_tenant("proj", "kb", create=True)
    await persist_snapshot(ctx, _snapshot("Tracking the flaky scheduler timeout"))

    primer = await build_session_primer("proj", "kb", "scheduler timeout")
    assert primer is not None
    assert "Tracking the flaky scheduler timeout" in primer
    assert "<recent-snapshots>" in primer


async def test_primer_none_for_empty_kb(local_engine):
    from br8n.agent.session_primer import build_session_primer
    from br8n.interfaces.mcp.tenancy import resolve_tenant

    resolve_tenant("empty", "kb", create=True)  # KB exists, but no findings/synopsis
    primer = await build_session_primer("empty", "kb", "anything")
    assert primer is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_session_primer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'br8n.agent.session_primer'`.

- [ ] **Step 3: Write the module**

Create `backend/br8n/agent/session_primer.py`:

```python
"""Build the broad session primer injected by the UserPromptSubmit hook.

    resume_preamble(depth="deep") + recent snapshots ─► additionalContext payload

The primer is mostly query-independent orientation (synopsis spine + recent capture
snapshots) seeded once by the session's first prompt's deep bands. Returns None when
the KB has nothing to orient with (empty/unknown KB) so the hook stays silent.

May raise (resolve_tenant on an unknown KB, embed/store errors) — the hook wraps the
call and suppresses on any exception.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from br8n.agent.resume import resume_preamble

_MAX_SNAPSHOTS = 3


async def build_session_primer(project: str, kb: str, query: str | None) -> str | None:
    """Return the additionalContext payload for (project, kb), or None if empty."""
    res = await resume_preamble(project, kb, query, depth="deep")

    listed = res.store.list_findings(res.ctx.kb_id, category="snapshot", limit=_MAX_SNAPSHOTS)
    snaps = listed.get("findings", []) if isinstance(listed, dict) else []

    # render_preamble emits "<synopsis>" only when the synopsis is non-empty and
    # "<finding " only when bands are admitted — so these substring checks reliably
    # detect orientation. No synopsis, no bands, and no snapshots → nothing to inject.
    has_orientation = (
        "<synopsis>" in res.preamble or "<finding " in res.preamble or bool(snaps)
    )
    if not has_orientation:
        return None

    parts = [res.preamble]
    if snaps:
        lines = ["<recent-snapshots>"]
        for f in snaps:
            title = escape(str(f.get("title", "")).strip())[:120]
            if title:
                lines.append(f"  <snapshot>{title}</snapshot>")
        lines.append("</recent-snapshots>")
        parts.append("\n".join(lines))
    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_session_primer.py -v`
Expected: PASS (2 passed). *(The capture-invalidation test is added in Task 4.)*

- [ ] **Step 5: Lint**

Run: `./.venv/bin/ruff check br8n/agent/session_primer.py tests/test_session_primer.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/br8n/agent/session_primer.py backend/tests/test_session_primer.py
git commit -m "feat(agent): build_session_primer — broad primer from resume core + snapshots"
```

---

## Task 3: Rewire the hook to cache-first

**Files:**
- Modify: `hooks/preamble-inject.py` (replace `_fetch`/`decide` with `_build`/`_inject` + cache layer)
- Rewrite: `backend/tests/hooks/test_preamble_inject_hook.py`

- [ ] **Step 1: Rewrite the test file**

Replace the entire contents of `backend/tests/hooks/test_preamble_inject_hook.py` with:

```python
"""Tests for hooks/preamble-inject.py — the cached UserPromptSubmit preamble hook.

Loads the hook by file path (it lives outside backend/) and pins the cache dir so the
real ~/.br8n is never touched.
"""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_HOOK_PATH = Path(__file__).parents[3] / "hooks" / "preamble-inject.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("preamble_inject", _HOOK_PATH)
    assert spec is not None and spec.loader is not None, f"Cannot load {_HOOK_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


_hook = _load_hook()
derive_target = _hook.derive_target


@pytest.fixture(autouse=True)
def cache_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("BR8N_PREAMBLE_CACHE_DIR", str(tmp_path))
    return tmp_path


def _run_main_with_stdin(payload):
    sys.stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    try:
        _hook.main()
    finally:
        sys.stdin = sys.__stdin__


# --- _inject --------------------------------------------------------------

def test_inject_shape():
    out = _hook._inject("<preamble>x</preamble>")
    parsed = json.loads(out)
    assert parsed["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert parsed["hookSpecificOutput"]["additionalContext"] == "<preamble>x</preamble>"


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


# --- main: cache hit / miss ----------------------------------------------

def test_main_cache_hit_injects_without_build(capsys, tmp_path):
    from br8n import preamble_cache

    preamble_cache.write("sess1", "repo", "dev", "<preamble>cached</preamble>")
    with (
        patch.object(_hook, "derive_target", return_value=("repo", "dev")),
        patch.object(_hook, "_build") as m_build,
    ):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "sess1"})
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["additionalContext"] == "<preamble>cached</preamble>"
    m_build.assert_not_called()


def test_main_cache_miss_builds_writes_injects(capsys, tmp_path):
    from br8n import preamble_cache

    with (
        patch.object(_hook, "derive_target", return_value=("repo", "dev")),
        patch.object(_hook, "_build", return_value="<preamble>fresh</preamble>"),
    ):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "sess2"})
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["additionalContext"] == "<preamble>fresh</preamble>"
    # Written to the cache for reuse next turn.
    assert preamble_cache.read("sess2", "repo", "dev") == "<preamble>fresh</preamble>"


def test_main_silent_when_build_none(capsys, tmp_path):
    from br8n import preamble_cache

    with (
        patch.object(_hook, "derive_target", return_value=("repo", "dev")),
        patch.object(_hook, "_build", return_value=None),
    ):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "sess3"})
    assert capsys.readouterr().out == ""
    assert preamble_cache.read("sess3", "repo", "dev") is None  # nothing cached


# --- main: suppress paths (unchanged from v1) -----------------------------

def test_main_silent_when_not_git(capsys, tmp_path):
    with patch.object(_hook, "derive_target", return_value=None):
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "s"})
    assert capsys.readouterr().out == ""


def test_main_silent_when_gate_disabled(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("BR8N_PREAMBLE_INJECT", "0")
    with patch.object(_hook, "derive_target", return_value=("repo", "dev")) as m:
        _run_main_with_stdin({"cwd": str(tmp_path), "prompt": "hi", "session_id": "s"})
    assert capsys.readouterr().out == ""
    m.assert_not_called()


def test_main_handles_malformed_stdin(capsys):
    _run_main_with_stdin("not json{{{")
    assert capsys.readouterr().out == ""


def test_main_handles_non_object_stdin(capsys):
    for payload in ("5", "[1, 2]", '"hello"', "null"):
        _run_main_with_stdin(payload)
        assert capsys.readouterr().out == ""


# --- _build fail-silent ---------------------------------------------------

def test_build_returns_none_on_error():
    """_build swallows a failed primer build and returns None (suppress)."""
    with patch(
        "br8n.agent.session_primer.build_session_primer",
        side_effect=RuntimeError("kb dev not found"),
    ):
        assert _hook._build("repo", "dev", "q") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/hooks/test_preamble_inject_hook.py -v`
Expected: FAIL — the hook still has v1 `_fetch`/`decide` and no `_inject`/`_build`/cache layer, so `_hook._inject` / `_hook._build` raise `AttributeError` and the cache-hit/miss tests fail.

- [ ] **Step 3: Rewrite the hook**

Replace the entire contents of `hooks/preamble-inject.py` with:

```python
"""br8n UserPromptSubmit hook — always-on cached preamble injection.

    python hooks/preamble-inject.py

Before each user turn, injects the current repo+branch KB's session primer as
additionalContext, so Claude answers grounded — no skill call, no visible tool call.
The primer is built once per session (the first turn imports br8n and composes a
broad orientation: synopsis + deep first-prompt bands + recent snapshots) and cached
to a stdlib-readable file; later turns read the file (no engine import) and inject it
verbatim. A capture clears the cache so the next turn rebuilds.

Design goals
------------
* **Silent.** hookSpecificOutput.additionalContext; nothing printed, no tool call.
* **Fast after turn 1.** Cache hits import only the stdlib br8n.preamble_cache (~ms);
  only a miss pays the ~1.5s engine import.
* **Non-blocking, fail-silent.** Not a git repo, empty KB, br8n unimportable, or any
  error → emit nothing, exit 0.
* **Importable for testing.** Logic in derive_target / _build / _inject; main() is glue.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def derive_target(cwd: str) -> tuple[str, str] | None:
    """Return (project, kb) = (toplevel basename, current branch), or None if not git.

    Matches skills/_shared/preamble-first.md and the capture path exactly: project is
    the repo folder name, kb is the git branch (via `git branch --show-current`, which
    handles unborn branches and is empty on detached HEAD → suppress)."""
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if top.returncode != 0:
            return None
        project = os.path.basename(top.stdout.strip())
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
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


def _build(project: str, kb: str, query: str) -> str | None:
    """Import br8n and build the session primer, or None on any error (fail-silent)."""
    try:
        import asyncio

        from br8n.agent.session_primer import build_session_primer

        return asyncio.run(build_session_primer(project, kb, query))
    except Exception:  # noqa: BLE001 — fail-silent: never break the turn
        return None


def _inject(payload: str) -> str:
    """Wrap the primer in the UserPromptSubmit context-injection JSON (silent inject)."""
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": payload,
            }
        }
    )


def main() -> None:
    """UserPromptSubmit entry point. Cache hit → inject; miss → build, cache, inject."""
    if os.getenv("BR8N_PREAMBLE_INJECT", "1") == "0":
        return
    try:
        raw = sys.stdin.read()
        ctx = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 — malformed stdin → silent
        return
    if not isinstance(ctx, dict):  # valid JSON but not an object (5, [..], "x") → silent
        return

    cwd = ctx.get("cwd") or (ctx.get("session") or {}).get("cwd") or os.getcwd()
    prompt = ctx.get("prompt") or ""
    session_id = ctx.get("session_id") or "default"

    target = derive_target(cwd)
    if target is None:
        return
    project, kb = target

    # Fast path: a cached primer for this session → inject without the heavy engine.
    try:
        from br8n import preamble_cache
    except Exception:  # noqa: BLE001 — br8n not importable → no cache, no primer
        return
    cached = preamble_cache.read(session_id, project, kb)
    if cached:
        print(_inject(cached))
        return

    # Miss: build the primer once, cache it, inject.
    primer = _build(project, kb, prompt)
    if primer is None:
        return
    preamble_cache.write(session_id, project, kb, primer)
    print(_inject(primer))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/hooks/test_preamble_inject_hook.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Lint**

Run: `./.venv/bin/ruff check ../hooks/preamble-inject.py tests/hooks/test_preamble_inject_hook.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add hooks/preamble-inject.py backend/tests/hooks/test_preamble_inject_hook.py
git commit -m "feat(hooks): cache-first session-primer injection (build once, reuse)"
```

---

## Task 4: Invalidate the cache on capture

**Files:**
- Modify: `backend/br8n/capture/service.py`
- Test: `backend/tests/test_session_primer.py` (add one test)

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/test_session_primer.py`:

```python
async def test_capture_invalidates_primer_cache(local_engine):
    from br8n import preamble_cache
    from br8n.capture.service import persist_snapshot
    from br8n.interfaces.mcp.tenancy import resolve_tenant

    # Seed a cached primer for the repo+branch the snapshot targets
    # (_snapshot uses project_path="/tmp/proj" → basename "proj", branch="main").
    preamble_cache.write("sessX", "proj", "main", "<preamble>stale</preamble>")
    assert preamble_cache.read("sessX", "proj", "main") == "<preamble>stale</preamble>"

    ctx = resolve_tenant("proj", "kb", create=True)
    await persist_snapshot(ctx, _snapshot("new work landed"))

    assert preamble_cache.read("sessX", "proj", "main") is None  # invalidated by capture
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_session_primer.py::test_capture_invalidates_primer_cache -v`
Expected: FAIL — `persist_snapshot` doesn't invalidate yet, so the stale entry survives.

- [ ] **Step 3: Wire invalidation into `persist_snapshot`**

In `backend/br8n/capture/service.py`, add this module-level helper (after the imports, before `persist_snapshot`):

```python
def _invalidate_primer_cache(snap: WorkspaceSnapshot) -> None:
    """Best-effort: clear the cached session primer so the next turn rebuilds with this
    snapshot. Keyed by (basename(project_path), branch) to match the hook's derivation.
    A cache error never breaks a capture."""
    try:
        import os

        from br8n import preamble_cache

        project = os.path.basename(snap.project_path.rstrip("/"))
        preamble_cache.invalidate(project, snap.branch or "")
    except Exception:  # noqa: BLE001 — invalidation is best-effort
        pass
```

Then, in `persist_snapshot`, call it right before `return finding_id`. The function becomes:

```python
async def persist_snapshot(ctx: TenantContext, snap: WorkspaceSnapshot) -> str:
    """Embed + insert snapshot as a Finding. Returns the new finding id.

    Fires a synopsis rebuild after write (fire-and-forget in the caller)
    so the resume card stays current without blocking the capture response.
    Also invalidates any cached session primer for this repo+branch so the next
    turn's injection rebuilds with this snapshot.
    """
    payload = snapshot_to_finding(snap)
    [embedding] = await embed_batch([payload["content"]])
    row = {
        "org_id": ctx.org_id,
        "kb_id": ctx.kb_id,
        "title": payload["title"],
        "content": payload["content"],
        "category": payload["category"],
        "confidence": 1.0,
        "tags": payload["tags"],
        "provenance": payload["provenance"],
        "embedding": embedding,
    }
    [finding_id] = await get_store(ctx.access_token).insert_findings([row])
    schedule_rebuild(ctx)
    _invalidate_primer_cache(snap)
    return finding_id
```

(Only the docstring line + the `_invalidate_primer_cache(snap)` call are added; the rest is unchanged. `WorkspaceSnapshot` is already imported in this file.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_session_primer.py -v`
Expected: PASS (3 passed — the two primer tests plus the new invalidation test).

- [ ] **Step 5: Lint**

Run: `./.venv/bin/ruff check br8n/capture/service.py tests/test_session_primer.py`
Expected: no errors.

- [ ] **Step 6: Full sweep + manual smoke**

Run (regression across the feature + neighbors):
`./.venv/bin/python -m pytest tests/test_preamble_cache.py tests/test_session_primer.py tests/hooks/test_preamble_inject_hook.py tests/test_resume_core.py tests/test_api_read_surfaces.py tests/test_engine_local.py -q`
Expected: all PASS.

Manual smoke against the real engine (first turn builds + caches; second turn hits cache). From repo root:
```bash
P=$(pwd); S="smoke-$$"
echo '{"cwd":"'"$P"'","prompt":"chat agent endpoint","session_id":"'"$S"'"}' | backend/.venv/bin/python hooks/preamble-inject.py; echo "turn1 exit=$?"
echo '{"cwd":"'"$P"'","prompt":"anything else","session_id":"'"$S"'"}' | backend/.venv/bin/python hooks/preamble-inject.py; echo "turn2 exit=$?"
ls ~/.br8n/preamble-cache/ 2>/dev/null | head
```
Expected: both exit 0; turn 1 may emit an injection (or empty if that KB has no orientation); if turn 1 injected, turn 2 emits the SAME payload (served from cache); a cache file exists for the session. No traceback. Then clean up the smoke cache file: `rm -f ~/.br8n/preamble-cache/*smoke-*` (optional).

- [ ] **Step 7: Commit**

```bash
git add backend/br8n/capture/service.py backend/tests/test_session_primer.py
git commit -m "feat(capture): invalidate cached session primer on snapshot persist"
```

---

## Self-Review

**Spec coverage:**
- Stdlib cache, hit avoids engine import → Task 1 (`preamble_cache.py`) + Step 6 import-time check. ✓
- Broad primer (synopsis + deep first-prompt bands + recent snapshots), None on empty KB → Task 2 (`build_session_primer`). ✓
- Cache-first hook (hit fast / miss build+write), `_fetch`→`_build`, `decide`→`_inject`, session_id keying, fail-silent → Task 3. ✓
- Capture invalidation via `persist_snapshot` → Task 4. ✓
- Per-session keying + capture refresh → Tasks 1 (key) + 4 (invalidate). ✓
- v1 coverage/`decide` tests removed → Task 3 rewrites the test file (no `test_decide_*`, no `test_main_silent_on_gap`). ✓
- Activity omitted from primer → Task 2 composes only synopsis + bands + snapshots. ✓
- `BR8N_PREAMBLE_INJECT` kill switch + non-object-stdin guard retained → Task 3 `main` + `test_main_silent_when_gate_disabled` / `test_main_handles_non_object_stdin`. ✓

**Placeholder scan:** none — every code step has complete code; every command has expected output.

**Type/name consistency:** `preamble_cache.read/write/invalidate/prune/cache_key` used identically across Tasks 1, 3, 4. `build_session_primer(project, kb, query)` defined in Task 2, called by `_build` in Task 3, patched in Task 3's `test_build_returns_none_on_error`. Hook helpers `derive_target`/`_build`/`_inject`/`main` consistent between the hook and its tests. The cache-dir env var `BR8N_PREAMBLE_CACHE_DIR` spelled identically in the module (Task 1), the fixtures (Tasks 2–3), and is honored by `_dir()`. `_invalidate_primer_cache(snap)` keys on `basename(project_path)` + `branch`, matching the hook's `derive_target` and the cache `cache_key`.
```
