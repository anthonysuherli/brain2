# Living Docs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make brain2 auto-generate and continuously update a two-layer, on-disk documentation tree (append-only session notes → debounced curated docs), plus a background change-driven auto-capture watcher — all non-blocking and fail-silent.

**Architecture:** A new `brain2/livingdocs/` backend package owns paths (`.brain2/` in the repo, git-ignored), the note policy (template + free-text steer), the docs-state bookkeeping, note persistence (note = a `category="note"` Finding *and* a markdown file), the snapshot→note fallback distiller, and the curated-tree distiller (content-inferred taxonomy, schema-optional). New MCP tools (`brain2_note`, `brain2_notes_policy_{get,set}`, `brain2_distill`) are the agent-facing surface; new skills (`/brain2:notes` with a HITL wizard, `/brain2:docs`) drive them. A `SessionStart` hook launches a non-LLM Python **watcher subprocess** that polls git and captures on real change; a `SessionEnd`/`Stop` hook writes the session note then signals a debounced distill. Everything degrades to silence when its env gate is off or anything fails.

**Tech Stack:** Python 3.11, Pydantic v2 (`BaseModel` config pattern), `pytest`, FastMCP (`mcp.server.fastmcp`), SQLite + sqlite-vec (local tier), the existing `Store` protocol, `embed_batch`, `resolve_tenant`, `schedule_rebuild`. Claude Code plugin hooks (`hooks/*.py` + `hooks.json`) and skills (`skills/*/SKILL.md`).

**Conventions:** Imports always `from brain2.*`. Run tests with `BRAIN2_BACKEND=local`. New env gates default **on** and are read with `os.getenv("X", "1") == "0"` guards (mirror `schedule_activity_update`). Every background path wraps work in `try/except` that logs and never raises (mirror `_run_activity_update`). Best-effort writes into the user repo use the `project_path` carried by the snapshot/tool call.

**Deviation from design doc (noted):** The design says the auto-capture loop is an `Agent(run_in_background)`. We implement it as a **non-LLM Python watcher subprocess** launched by the `SessionStart` hook (cheaper, more robust, truly non-blocking, no sleeping LLM agent). It still satisfies "captures periodically done in parallel in the background." Auto-captures are deterministic (branch/diff/files, no hypothesis); rich reasoning comes from the agent-written session note.

**Worktree:** `.worktrees/living-docs` on branch `feat/living-docs`. Deps installed; baseline `BRAIN2_BACKEND=local .venv/bin/pytest -q` = 204 passed, 1 skipped. Run all commands from `backend/` with `.venv/bin/...`.

---

## Step 0 — Config + package skeleton

### Task 0.1: Add `LivingDocsConfig` to AppConfig

**Files:**
- Modify: `backend/brain2/config.py` (add class near `ActivityConfig` ~line 142; wire into `AppConfig` ~line 262)
- Test: `backend/tests/test_livingdocs_config.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_livingdocs_config.py
from brain2.config import get_config


def test_living_docs_config_defaults():
    cfg = get_config().living_docs
    assert cfg.notes_dirname == "notes"
    assert cfg.docs_dirname == "docs"
    assert cfg.root_dirname == ".brain2"
    assert cfg.distill_debounce_n == 3
    assert cfg.distill_debounce_minutes == 60
    assert cfg.cluster_min_notes == 5
    assert cfg.watch_interval_seconds == 180
```

**Step 2: Run it, expect FAIL** — `Run: BRAIN2_BACKEND=local .venv/bin/pytest tests/test_livingdocs_config.py -q` → `AttributeError: 'AppConfig' object has no attribute 'living_docs'`.

**Step 3: Implement** — add to `config.py`:

```python
class LivingDocsConfig(BaseModel):
    """Living Docs — two-layer on-disk documentation (notes → curated tree)."""
    root_dirname: str = ".brain2"
    notes_dirname: str = "notes"
    docs_dirname: str = "docs"
    policy_filename: str = "notes-policy.json"
    state_filename: str = "docs-state.json"
    # Distill debounce: re-distill when N new notes OR T minutes since last run.
    distill_debounce_n: int = 3
    distill_debounce_minutes: int = 60
    # Flat until this many notes exist, then allow taxonomy clustering.
    cluster_min_notes: int = 5
    distill_model: str = "claude-haiku-4-5"
    distill_fallback_model: str = "openai/gpt-4o-mini"
    temperature: float = 0.0
    # Auto-capture watcher.
    watch_interval_seconds: int = 180
```

Then add the field to `AppConfig` (alongside `activity: ActivityConfig = ActivityConfig()`):

```python
    living_docs: LivingDocsConfig = LivingDocsConfig()
```

**Step 4: Run test, expect PASS.**

**Step 5: Commit**

```bash
git add backend/brain2/config.py backend/tests/test_livingdocs_config.py
git commit -m "feat(livingdocs): add LivingDocsConfig"
```

### Task 0.2: Create the package skeleton

**Files:**
- Create: `backend/brain2/livingdocs/__init__.py` (empty docstring module)

**Step 1:** Write `backend/brain2/livingdocs/__init__.py`:

```python
"""Living Docs — two-layer on-disk documentation (session notes → curated tree)."""
```

**Step 2: Commit**

```bash
git add backend/brain2/livingdocs/__init__.py
git commit -m "feat(livingdocs): package skeleton"
```

---

## Step 1 — On-disk layout (`paths.py`)

### Task 1.1: Path resolver + layout bootstrap

**Files:**
- Create: `backend/brain2/livingdocs/paths.py`
- Test: `backend/tests/test_livingdocs_paths.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_livingdocs_paths.py
from pathlib import Path
from brain2.livingdocs.paths import DocPaths, ensure_layout


def test_paths_layout(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    assert p.root == tmp_path / ".brain2"
    assert p.notes_dir == tmp_path / ".brain2" / "notes" / "main"
    assert p.docs_dir == tmp_path / ".brain2" / "docs"
    assert p.policy_path == tmp_path / ".brain2" / "notes-policy.json"
    assert p.state_path == tmp_path / ".brain2" / "docs-state.json"


def test_ensure_layout_creates_dirs_and_gitignore(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="feat/x")
    ensure_layout(p)
    assert p.notes_dir.is_dir()
    assert p.docs_dir.is_dir()
    gitignore = (tmp_path / ".brain2" / ".gitignore")
    assert gitignore.read_text().strip() == "*"


def test_kb_with_slashes_is_filesystem_safe(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="feature/auth-fix")
    # slashes in branch must not escape the notes dir
    assert p.notes_dir == tmp_path / ".brain2" / "notes" / "feature__auth-fix"
```

**Step 2: Run, expect FAIL** (module missing).

**Step 3: Implement** `paths.py`:

```python
"""Resolve and bootstrap the on-disk .brain2/ Living Docs layout."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from brain2.config import get_config


def _safe(segment: str) -> str:
    """Filesystem-safe single path segment (branch names contain '/')."""
    return re.sub(r"[^A-Za-z0-9._-]+", "__", segment.strip()) or "default"


@dataclass(frozen=True)
class DocPaths:
    project_path: str
    kb: str

    @property
    def _cfg(self):
        return get_config().living_docs

    @property
    def root(self) -> Path:
        return Path(self.project_path) / self._cfg.root_dirname

    @property
    def notes_dir(self) -> Path:
        return self.root / self._cfg.notes_dirname / _safe(self.kb)

    @property
    def docs_dir(self) -> Path:
        return self.root / self._cfg.docs_dirname

    @property
    def policy_path(self) -> Path:
        return self.root / self._cfg.policy_filename

    @property
    def state_path(self) -> Path:
        return self.root / self._cfg.state_filename


def ensure_layout(paths: DocPaths) -> None:
    """Create dirs + a self-ignoring .gitignore (`*`) so .brain2/ is never committed."""
    paths.notes_dir.mkdir(parents=True, exist_ok=True)
    paths.docs_dir.mkdir(parents=True, exist_ok=True)
    gi = paths.root / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n")
```

**Step 4: Run test, expect PASS.**

**Step 5: Commit**

```bash
git add backend/brain2/livingdocs/paths.py backend/tests/test_livingdocs_paths.py
git commit -m "feat(livingdocs): .brain2/ path resolver + layout bootstrap"
```

---

## Step 2 — Notes as Findings + files (`notes.py`)

### Task 2.1: Note policy model + load/save (`policy.py`)

**Files:**
- Create: `backend/brain2/livingdocs/policy.py`
- Test: `backend/tests/test_livingdocs_policy.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_livingdocs_policy.py
from brain2.livingdocs.paths import DocPaths
from brain2.livingdocs.policy import NotePolicy, load_policy, save_policy, default_policy


def test_default_policy_sections():
    pol = default_policy()
    names = [s.name for s in pol.sections if s.enabled]
    assert names == ["Decisions", "Changes", "Open Questions", "Next Steps"]
    assert pol.steer == ""


def test_load_returns_default_when_absent(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    assert load_policy(p) == default_policy()


def test_save_then_load_roundtrip(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    pol = default_policy()
    pol.steer = "focus on architecture; skip dep bumps"
    save_policy(p, pol)
    assert load_policy(p).steer == "focus on architecture; skip dep bumps"
```

**Step 2: Run, expect FAIL.**

**Step 3: Implement** `policy.py`:

```python
"""Per-KB note-taking policy: section template + free-text steer."""
from __future__ import annotations

import json

from pydantic import BaseModel

from brain2.livingdocs.paths import DocPaths, ensure_layout

_DEFAULT_SECTIONS = ["Decisions", "Changes", "Open Questions", "Next Steps"]


class NoteSection(BaseModel):
    name: str
    enabled: bool = True


class NotePolicy(BaseModel):
    sections: list[NoteSection]
    steer: str = ""


def default_policy() -> NotePolicy:
    return NotePolicy(sections=[NoteSection(name=n) for n in _DEFAULT_SECTIONS])


def load_policy(paths: DocPaths) -> NotePolicy:
    try:
        raw = paths.policy_path.read_text()
    except (FileNotFoundError, OSError):
        return default_policy()
    try:
        return NotePolicy.model_validate_json(raw)
    except Exception:  # noqa: BLE001 — corrupt file → fall back, never crash
        return default_policy()


def save_policy(paths: DocPaths, policy: NotePolicy) -> None:
    ensure_layout(paths)
    paths.policy_path.write_text(json.dumps(policy.model_dump(), indent=2) + "\n")
```

**Step 4: Run, expect PASS. Step 5: Commit**

```bash
git add backend/brain2/livingdocs/policy.py backend/tests/test_livingdocs_policy.py
git commit -m "feat(livingdocs): note policy model + load/save"
```

### Task 2.2: Persist a note (Finding + file)

**Files:**
- Create: `backend/brain2/livingdocs/notes.py`
- Test: `backend/tests/test_livingdocs_notes.py`

**Step 1: Write the failing test** (uses local SQLite store via `resolve_tenant`):

```python
# backend/tests/test_livingdocs_notes.py
import os
import pytest
from brain2.interfaces.mcp.tenancy import resolve_tenant
from brain2.livingdocs.notes import persist_note
from brain2.livingdocs.paths import DocPaths
from brain2.store import get_store


@pytest.mark.asyncio
async def test_persist_note_writes_finding_and_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))
    ctx = resolve_tenant("proj", "main", create=True)
    note_md = "# Session\n\n## Decisions\nChose X over Y."
    res = await persist_note(
        ctx, project_path=str(tmp_path), kb="main",
        content=note_md, session_id="sess-123", title="Chose X over Y",
    )
    # Finding persisted
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    listed = store.list_findings(ctx.kb_id, category="note")
    assert listed["count"] == 1
    # File written under .brain2/notes/main/
    p = DocPaths(project_path=str(tmp_path), kb="main")
    files = list(p.notes_dir.glob("*.md"))
    assert len(files) == 1
    assert "Chose X over Y" in files[0].read_text()
    assert res["finding_id"]
    assert res["note_path"].endswith(".md")
```

**Step 2: Run, expect FAIL.**

**Step 3: Implement** `notes.py` (mirror `capture/service.py`):

```python
"""Persist a session note as a `note` Finding AND a markdown file."""
from __future__ import annotations

import re

from brain2.agent.state import TenantContext
from brain2.agent.synopsis import schedule_rebuild
from brain2.clients.embeddings import embed_batch
from brain2.livingdocs.paths import DocPaths, ensure_layout
from brain2.store import get_store


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:48] or "note")


def _note_filename(captured_at: str, title: str) -> str:
    # captured_at = ISO-8601; produce 2026-06-03-1430-slug.md
    stamp = captured_at[:16].replace("-", "").replace(":", "")  # 20260603T1430
    stamp = stamp.replace("T", "-")
    return f"{captured_at[:10]}-{captured_at[11:16].replace(':','')}-{_slug(title)}.md"


async def persist_note(
    ctx: TenantContext,
    *,
    project_path: str,
    kb: str,
    content: str,
    session_id: str,
    title: str,
    captured_at: str = "",
    source: str = "agent",
) -> dict:
    """Embed+insert the note as a `note` Finding, write the markdown file. Returns
    {finding_id, note_path}. The Finding feeds resume/search/activity-KG; the file
    is the rendered journal entry."""
    from datetime import datetime, timezone
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()

    row = {
        "org_id": ctx.org_id,
        "kb_id": ctx.kb_id,
        "title": title[:120],
        "content": content,
        "category": "note",
        "confidence": 1.0 if source == "agent" else 0.6,
        "tags": ["note", source],
        "provenance": [{"source": f"brain2-livingdocs-{source}", "session": session_id, "path": project_path}],
    }
    [embedding] = await embed_batch([content])
    row["embedding"] = embedding
    [finding_id] = await get_store(ctx.access_token).insert_findings([row])

    paths = DocPaths(project_path=project_path, kb=kb)
    ensure_layout(paths)
    note_path = paths.notes_dir / _note_filename(captured_at, title)
    note_path.write_text(content if content.endswith("\n") else content + "\n")

    schedule_rebuild(ctx)
    return {"finding_id": finding_id, "note_path": str(note_path)}
```

**Step 4: Run, expect PASS. Step 5: Commit**

```bash
git add backend/brain2/livingdocs/notes.py backend/tests/test_livingdocs_notes.py
git commit -m "feat(livingdocs): persist note as Finding + markdown file"
```

### Task 2.3: `brain2_note` MCP tool + `Stop` hook + `_shared/session-note.md`

**Files:**
- Modify: `backend/brain2/interfaces/mcp/server.py` (add tool near `brain2_capture`)
- Create: `hooks/session-note.py`
- Modify: `hooks/hooks.json` (add `Stop` matcher)
- Create: `skills/_shared/session-note.md`
- Test: `backend/tests/test_note_tool.py`

**Step 1: Write the failing test** for the tool:

```python
# backend/tests/test_note_tool.py
import pytest
from brain2.interfaces.mcp import server


@pytest.mark.asyncio
async def test_brain2_note_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))
    res = await server.brain2_note.fn(
        project="proj", kb="main", project_path=str(tmp_path),
        content="## Decisions\nX.", session_id="s1", title="t",
    )
    assert res["finding_id"]
    assert res["note_path"].endswith(".md")
```

> Note: FastMCP wraps functions; call the underlying via `.fn` (confirm in repo; if the tool object exposes the coroutine differently, adjust the test to import the inner function — keep the inner logic in a plain `async def _note_impl(...)` and have the `@mcp.tool()` call it, so tests target `_note_impl`). **Prefer the `_impl` pattern** to keep tests decoupled from FastMCP internals.

**Step 2: Implement** — in `server.py` add:

```python
from brain2.livingdocs.distill import schedule_distill  # add at top
from brain2.livingdocs.notes import persist_note


async def _note_impl(project, kb, project_path, content, session_id, title, captured_at="", source="agent"):
    ctx = resolve_tenant(project, kb, create=True)
    res = await persist_note(
        ctx, project_path=project_path, kb=kb, content=content,
        session_id=session_id, title=title, captured_at=captured_at, source=source,
    )
    schedule_distill(ctx, project_path=project_path, kb=kb)  # debounced, fire-and-forget
    return {**res, "project": project, "kb": kb}


@mcp.tool()
async def brain2_note(
    project: str, kb: str, project_path: str, content: str,
    session_id: str, title: str, captured_at: str = "", source: str = "agent",
) -> dict:
    """Persist a session note: a `note` Finding (searchable, feeds resume) AND a
    markdown file under .brain2/notes/<kb>/. Then schedules a debounced re-distill of
    the curated doc tree. Called by the Stop hook at session end. `content` should be
    rendered per the KB's note policy (see brain2_notes_policy_get)."""
    return await _note_impl(project, kb, project_path, content, session_id, title, captured_at, source)
```

(Adjust the test to target `server._note_impl` instead of `.fn`.)

**Step 3:** Create `hooks/session-note.py` — a `Stop`/`SessionEnd` hook that emits a directive instructing Claude to write the note. Mirror `first-run-init.py` structure (read stdin JSON → derive project/kb/cwd → print `{"additionalContext": ...}`; silent on non-git / errors). The directive tells Claude to:
1. read the note policy (`mcp__brain2__brain2_notes_policy_get`),
2. summarize the just-finished conversation into those sections + honoring the steer,
3. call `mcp__brain2__brain2_note(project, kb, project_path, content, session_id, title)`,
4. do it without blocking; if nothing substantive happened, skip.

Gate the whole hook on `BRAIN2_LIVING_DOCS != "0"`.

**Step 4:** Add to `hooks/hooks.json`:

```json
    "Stop": [
      { "matcher": "*", "hooks": [
        { "type": "command", "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/session-note.py", "timeout": 30 }
      ]}
    ]
```

**Step 5:** Write `skills/_shared/session-note.md` — the canonical note-writing convention (the same instructions, referenced by the hook directive and reusable by `/brain2:notes` manual runs).

**Step 6: Run** `BRAIN2_BACKEND=local .venv/bin/pytest tests/test_note_tool.py -q` → PASS. **Commit**

```bash
git add backend/brain2/interfaces/mcp/server.py backend/tests/test_note_tool.py hooks/session-note.py hooks/hooks.json skills/_shared/session-note.md
git commit -m "feat(livingdocs): brain2_note tool + Stop hook + session-note convention"
```

> **Dependency note:** `_note_impl` imports `schedule_distill` from Step 6. To keep commits green, implement Task 6.1 (`distill.schedule_distill` as a no-op-capable stub) *before* this task, or temporarily inline a `def schedule_distill(*a, **k): pass` and replace it in Step 6. Recommended: reorder — do Task 6.1's `schedule_distill` signature first.

---

## Step 3 — `/brain2:notes` skill + policy tools + wizard

### Task 3.1: Policy get/set MCP tools

**Files:**
- Modify: `backend/brain2/interfaces/mcp/server.py`
- Test: `backend/tests/test_policy_tools.py`

**Step 1: Write failing test**

```python
# backend/tests/test_policy_tools.py
import pytest
from brain2.interfaces.mcp import server


def test_policy_get_default_then_set(tmp_path):
    g = server._policy_get_impl("proj", "main", str(tmp_path))
    assert [s["name"] for s in g["policy"]["sections"]] == [
        "Decisions", "Changes", "Open Questions", "Next Steps"]
    server._policy_set_impl("proj", "main", str(tmp_path),
                            {"sections": [{"name": "Decisions", "enabled": True}],
                             "steer": "be terse"})
    g2 = server._policy_get_impl("proj", "main", str(tmp_path))
    assert g2["policy"]["steer"] == "be terse"
    assert len(g2["policy"]["sections"]) == 1
```

**Step 2: Implement** `_policy_get_impl` / `_policy_set_impl` + thin `@mcp.tool()` wrappers `brain2_notes_policy_get` / `brain2_notes_policy_set` using `load_policy`/`save_policy`/`NotePolicy` and `DocPaths`. Return `{"policy": <dump>, "project", "kb"}`. `set` validates via `NotePolicy.model_validate(...)`; on validation error return `{"errors": [...]}`.

**Step 3: Run, PASS. Commit**

```bash
git add backend/brain2/interfaces/mcp/server.py backend/tests/test_policy_tools.py
git commit -m "feat(livingdocs): notes-policy get/set MCP tools"
```

### Task 3.2: `/brain2:notes` skill + wizard convention

**Files:**
- Create: `skills/notes/SKILL.md`
- Create: `skills/_shared/notes-policy-wizard.md`
- Modify: `.claude-plugin/plugin.json` (add `"./skills/notes"`)

**Step 1:** Write `skills/notes/SKILL.md` (frontmatter `name: notes` + description). Modes:
- no args → `brain2_notes_policy_get` and print the current template + steer.
- `<free text>` → set the steer via `brain2_notes_policy_set` (keep existing sections).
- `--wizard` → run `_shared/notes-policy-wizard.md`.

**Step 2:** Write `skills/_shared/notes-policy-wizard.md` modeled on `kg-schema-wizard.md`: a HITL loop asking **one multiple-choice question at a time** (which sections to keep/add, level of detail, what to skip, free-text steer), then persist via `brain2_notes_policy_set` at a turn boundary. Reference the design's "offer once, opt-in" principle: never auto-launch; only on `/brain2:notes --wizard`.

**Step 3:** Add `"./skills/notes"` to the `skills` array in `.claude-plugin/plugin.json`.

**Step 4:** No unit test (Markdown skills). Sanity-check JSON validity:

```bash
python -c "import json,sys; json.load(open('.claude-plugin/plugin.json')); print('ok')"
```

**Step 5: Commit**

```bash
git add skills/notes/SKILL.md skills/_shared/notes-policy-wizard.md .claude-plugin/plugin.json
git commit -m "feat(livingdocs): /brain2:notes skill + policy wizard"
```

---

## Step 4 — Auto-capture watcher (`watch.py`) + SessionStart launch

### Task 4.1: Change-detection fingerprint

**Files:**
- Create: `backend/brain2/livingdocs/watch.py`
- Test: `backend/tests/test_livingdocs_watch.py`

**Step 1: Write failing test** (pure-function fingerprint; no subprocess loop under test):

```python
# backend/tests/test_livingdocs_watch.py
from brain2.livingdocs.watch import fingerprint, changed


def test_changed_detects_diff():
    a = fingerprint(branch="main", diff_stat="1 file", open_files=["x.py"])
    b = fingerprint(branch="main", diff_stat="1 file", open_files=["x.py"])
    c = fingerprint(branch="main", diff_stat="2 files", open_files=["x.py"])
    assert changed(a, b) is False
    assert changed(a, c) is True
    assert changed(None, a) is True
```

**Step 2: Implement** `watch.py` with:
- `fingerprint(branch, diff_stat, open_files) -> str` (stable hash, e.g. `hashlib.sha256` of a joined tuple);
- `changed(prev, cur) -> bool`;
- `read_git_state(cwd) -> dict` (subprocess `git branch --show-current`, `git diff --stat`; best-effort, returns `{}` on failure);
- `async def capture_once(project, kb, project_path, state) -> str|None` calling the existing in-process capture path (`resolve_tenant` + `persist_snapshot` + `schedule_activity_update`) with `trigger="idle"`, no hypothesis;
- `def run_watch(cwd, interval, stop_path)` — the loop: every `interval`s read git state, capture on change, exit when `stop_path` exists or parent died. Gate on `BRAIN2_AUTO_CAPTURE != "0"` and `BRAIN2_LIVING_DOCS != "0"`.
- `if __name__ == "__main__": run_watch(...)` reading args/env (`BRAIN2_WATCH_CWD`, `BRAIN2_WATCH_STOP`, interval from config).

Only `fingerprint`/`changed` are unit-tested; the loop is integration-only.

**Step 3: Run, PASS. Commit**

```bash
git add backend/brain2/livingdocs/watch.py backend/tests/test_livingdocs_watch.py
git commit -m "feat(livingdocs): auto-capture watcher (fingerprint + change-driven loop)"
```

### Task 4.2: Launch watcher from SessionStart; stop on SessionEnd

**Files:**
- Modify: `hooks/first-run-init.py` (append a best-effort watcher launch at end of `main()`), OR create `hooks/auto-capture.py` as a second `SessionStart` hook (preferred: keep concerns separate).
- Create: `hooks/auto-capture.py`
- Modify: `hooks/hooks.json` (second `SessionStart` command + a `SessionEnd` stop)
- Test: `backend/tests/test_auto_capture_hook.py`

**Step 1: Write failing test** for the launch decision (pure function):

```python
# backend/tests/test_auto_capture_hook.py
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "auto_capture", pathlib.Path("hooks/auto-capture.py"))
ac = importlib.util.module_from_spec(spec); spec.loader.exec_module(ac)


def test_should_launch_respects_gate(monkeypatch):
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "0")
    assert ac.should_launch("/some/git/repo") is False
    monkeypatch.setenv("BRAIN2_AUTO_CAPTURE", "1")
    assert ac.should_launch("/nonexistent/not/a/repo") is False  # not a git repo
```

**Step 2: Implement** `hooks/auto-capture.py`:
- `should_launch(cwd) -> bool` — git repo? + gates on; + not already running (check a pidfile under the repo's `.brain2/`).
- `main()` — read stdin JSON, derive cwd, if `should_launch`: write a stop-file path, `subprocess.Popen([sys.executable, "-m", "brain2.livingdocs.watch"], env={..."BRAIN2_WATCH_CWD", "BRAIN2_WATCH_STOP"...}, start_new_session=True)` (detached), record pid. Silent on any failure.
- A `SessionEnd` branch (or separate `hooks/auto-capture-stop.py`) that `touch`es the stop-file so the watcher exits cleanly.

**Step 3:** Wire `hooks.json`: add `auto-capture.py` to `SessionStart` and a `SessionEnd` entry to stop it.

**Step 4: Run, PASS. Commit**

```bash
git add hooks/auto-capture.py hooks/hooks.json backend/tests/test_auto_capture_hook.py
git commit -m "feat(livingdocs): launch change-driven watcher on SessionStart, stop on SessionEnd"
```

---

## Step 5 — Backend fallback distiller (snapshots → note)

### Task 5.1: Distill a note from a session's snapshots

**Files:**
- Create: `backend/brain2/livingdocs/fallback.py`
- Test: `backend/tests/test_livingdocs_fallback.py`

**Step 1: Write failing test** (deterministic shape; LLM call mocked/gated off → deterministic synth):

```python
# backend/tests/test_livingdocs_fallback.py
from brain2.livingdocs.fallback import synth_note_markdown


def test_synth_note_markdown_from_snapshots():
    snaps = [
        {"title": "fix auth race", "content": "**Hypothesis**: fix auth race\n**Branch**: `main`"},
        {"title": "Working on auth.py", "content": "**Cursor**: `auth.py:42`"},
    ]
    md = synth_note_markdown(snaps, policy_sections=["Decisions", "Changes"])
    assert md.startswith("#")
    assert "## Changes" in md
    assert "auth" in md.lower()
```

**Step 2: Implement** `fallback.py`:
- `synth_note_markdown(snaps, policy_sections) -> str` — deterministic assembly: title from latest hypothesis/snapshot; a "Changes" section listing branches/files/diffs seen; other policy sections left as headers with a "(no data)" line. (Pure, testable.)
- `async def distill_fallback_note(ctx, *, project_path, kb, session_id) -> dict|None` — fetch the session's snapshots (`store.list_findings(kb_id, category="snapshot")`, filter by `provenance.session`/recency), call `synth_note_markdown`, then `persist_note(..., source="backend")`. Best-effort; returns None on no snapshots. Optionally LLM-upgrade the body when `BRAIN2_LIVING_DOCS_LLM != "0"` (reuse the activity task-LLM client pattern), falling back to the deterministic body on any failure.

**Step 3: Run, PASS. Commit**

```bash
git add backend/brain2/livingdocs/fallback.py backend/tests/test_livingdocs_fallback.py
git commit -m "feat(livingdocs): backend fallback note distiller (snapshots->note)"
```

> The fallback is invoked when no agent note exists for a session — e.g. a `SessionEnd` path that checks for a recent `note` Finding for `session_id` and, if absent, calls `distill_fallback_note`. Wire this into `hooks/session-note.py` as the else-branch directive OR a small scheduled call. Keep it best-effort.

---

## Step 6 — Distill loop (taxonomy inference + doc-tree writer + debounce)

### Task 6.1: Docs-state model + debounce decision (`state.py`)

> **Do this task first if following the dependency note in Task 2.3** (it defines `schedule_distill`'s home and the state file).

**Files:**
- Create: `backend/brain2/livingdocs/state.py`
- Test: `backend/tests/test_livingdocs_state.py`

**Step 1: Write failing test**

```python
# backend/tests/test_livingdocs_state.py
from brain2.livingdocs.paths import DocPaths
from brain2.livingdocs.state import load_state, save_state, DocsState, should_distill


def test_state_roundtrip_and_debounce(tmp_path):
    p = DocPaths(project_path=str(tmp_path), kb="main")
    st = load_state(p)
    assert st.notes_since_distill == 0
    st.notes_since_distill = 3
    save_state(p, st)
    assert load_state(p).notes_since_distill == 3
    # N threshold reached
    assert should_distill(st, debounce_n=3, debounce_minutes=60) is True
    st.notes_since_distill = 1
    assert should_distill(st, debounce_n=3, debounce_minutes=60, now_iso="1970-01-01T00:00:00+00:00") is False
```

**Step 2: Implement** `state.py`:
- `class DocsState(BaseModel)`: `taxonomy: dict[str, list[str]] = {}` (folder → note-file basenames or topic keys), `notes_since_distill: int = 0`, `last_distill_at: str = ""`.
- `load_state` / `save_state` (mirror policy load/save; default on missing/corrupt).
- `should_distill(state, *, debounce_n, debounce_minutes, now_iso=None) -> bool` — True when `notes_since_distill >= debounce_n` OR minutes since `last_distill_at` >= `debounce_minutes` (and there is ≥1 pending note).

**Step 3: Run, PASS. Commit**

```bash
git add backend/brain2/livingdocs/state.py backend/tests/test_livingdocs_state.py
git commit -m "feat(livingdocs): docs-state model + debounce decision"
```

### Task 6.2: Taxonomy inference (pure) + doc-tree writer

**Files:**
- Create: `backend/brain2/livingdocs/distill.py`
- Test: `backend/tests/test_livingdocs_distill.py`

**Step 1: Write failing test** for the pure pieces:

```python
# backend/tests/test_livingdocs_distill.py
from brain2.livingdocs.distill import plan_layout


def test_flat_until_min_notes():
    notes = [{"title": f"n{i}", "topic": None} for i in range(3)]
    layout = plan_layout(notes, cluster_min_notes=5, schema=None)
    assert all(entry["folder"] == "" for entry in layout)  # flat


def test_clusters_when_enough_and_topics_present():
    notes = [{"title": "auth race", "topic": "auth"} for _ in range(3)] + \
            [{"title": "ui tweak", "topic": "ui"} for _ in range(3)]
    layout = plan_layout(notes, cluster_min_notes=5, schema=None)
    folders = {e["folder"] for e in layout}
    assert "auth" in folders and "ui" in folders


def test_schema_overrides_inferred():
    notes = [{"title": "x", "topic": "auth"}]
    layout = plan_layout(notes, cluster_min_notes=1, schema=["security", "ui"])
    assert all(e["folder"] in {"security", "ui", ""} for e in layout)
```

**Step 2: Implement** `distill.py`:
- `plan_layout(notes, *, cluster_min_notes, schema) -> list[dict]` — pure: flat (`folder=""`) until `len(notes) >= cluster_min_notes`; then group by `topic`; if `schema` (list of folder names) given, map each note's topic to the nearest schema folder (string match → else `""`). Deterministic; the *topic* per note is provided by the LLM step (or `None`).
- `async def _infer_topics(notes) -> list[str|None]` — gated LLM pass (`BRAIN2_LIVING_DOCS_LLM`) that tags each note with a short topic; deterministic fallback = `None` (→ flat). Mirror activity `_task_label` gating.
- `async def run_distill(ctx, *, project_path, kb) -> dict` — load note-Findings (`list_findings(kb_id, category="note")`), `_infer_topics`, `plan_layout` (schema from `get_kg_intent` node_types if set, else None), write/refresh `.brain2/docs/<folder>/<slug>.md` files (curated summary per cluster — concatenated/deduped note bodies; **not** re-ingested as Findings), update + save `DocsState` (reset `notes_since_distill`, stamp `last_distill_at`, store taxonomy). Best-effort.
- `schedule_distill(ctx, *, project_path, kb)` — fire-and-forget, debounced: bump `notes_since_distill`, `should_distill?` → `asyncio.create_task(run_distill(...))` held in a module `_BG_TASKS` set (mirror `schedule_activity_update`). No-op when `BRAIN2_LIVING_DOCS == "0"`.

**Step 3: Run, PASS. Commit**

```bash
git add backend/brain2/livingdocs/distill.py backend/tests/test_livingdocs_distill.py
git commit -m "feat(livingdocs): taxonomy inference + debounced doc-tree distiller"
```

### Task 6.3: Integration — note triggers debounced distill writes files

**Files:**
- Test: `backend/tests/test_livingdocs_integration.py`

**Step 1: Write the test** — persist `cluster_min_notes` notes via `_note_impl` (forcing distill by setting `debounce_n=1` via monkeypatched config or calling `run_distill` directly), assert files appear under `.brain2/docs/`. Keep it deterministic by calling `run_distill` directly (avoid racing the fire-and-forget task):

```python
# backend/tests/test_livingdocs_integration.py
import pytest
from brain2.interfaces.mcp.tenancy import resolve_tenant
from brain2.livingdocs.distill import run_distill
from brain2.livingdocs.notes import persist_note
from brain2.livingdocs.paths import DocPaths


@pytest.mark.asyncio
async def test_notes_distill_to_doc_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN2_BACKEND", "local")
    monkeypatch.setenv("BRAIN2_DB_PATH", str(tmp_path / "brain.db"))
    monkeypatch.setenv("BRAIN2_LIVING_DOCS_LLM", "0")  # deterministic → flat
    ctx = resolve_tenant("proj", "main", create=True)
    for i in range(3):
        await persist_note(ctx, project_path=str(tmp_path), kb="main",
                           content=f"## Decisions\nDecision {i}.", session_id=f"s{i}", title=f"note {i}")
    await run_distill(ctx, project_path=str(tmp_path), kb="main")
    docs = list((DocPaths(project_path=str(tmp_path), kb="main").docs_dir).rglob("*.md"))
    assert docs  # curated files written
```

**Step 2: Run, PASS. Step 3: Commit**

```bash
git add backend/tests/test_livingdocs_integration.py
git commit -m "test(livingdocs): notes distill into the curated doc tree"
```

---

## Step 7 — `/brain2:docs` skill + `brain2_distill` tool

### Task 7.1: `brain2_distill` MCP tool

**Files:**
- Modify: `backend/brain2/interfaces/mcp/server.py`
- Test: `backend/tests/test_distill_tool.py`

**Step 1: Write failing test** — `server._distill_impl("proj","main",project_path, force=True)` returns `{"distilled": True, "doc_count": N}` after notes exist.

**Step 2: Implement** `_distill_impl` + `@mcp.tool() brain2_distill(project, kb, project_path, force=False)` — `force=True` calls `run_distill` immediately; else respects debounce via `schedule_distill` and reports whether it ran. Return doc-file count under `.brain2/docs/`.

**Step 3: Run, PASS. Commit**

```bash
git add backend/brain2/interfaces/mcp/server.py backend/tests/test_distill_tool.py
git commit -m "feat(livingdocs): brain2_distill tool (force/debounced)"
```

### Task 7.2: `/brain2:docs` skill

**Files:**
- Create: `skills/docs/SKILL.md`
- Modify: `.claude-plugin/plugin.json` (add `"./skills/docs"`)

**Step 1:** Write `skills/docs/SKILL.md` (frontmatter `name: docs` + description). Behavior: resolve project/kb/project_path; list/read `.brain2/docs/` (use the agent's own file tools to read the tree and present it); `--rebuild` → `brain2_distill(force=True)` then show the refreshed tree.

**Step 2:** Add `"./skills/docs"` to `plugin.json`; validate JSON.

**Step 3: Commit**

```bash
git add skills/docs/SKILL.md .claude-plugin/plugin.json
git commit -m "feat(livingdocs): /brain2:docs skill (browse + --rebuild)"
```

---

## Step 8 — Full suite + docs

### Task 8.1: Green the whole suite

**Step 1:** `Run: BRAIN2_BACKEND=local .venv/bin/pytest -q` → expect **all prior 204 + new tests pass**, 0 failures. Fix any regressions (likely import-time issues if `schedule_distill` wiring is off).

**Step 2: Commit** any fixes.

### Task 8.2: Update CLAUDE.md + design status

**Files:**
- Modify: `CLAUDE.md` (add Living Docs to "What's new", Phase status, MCP tools table, Plugin skills list)
- Modify: `docs/plans/2026-06-03-living-docs-design.md` (status → implemented; note the watcher deviation)

**Step 1:** Document: new `brain2/livingdocs/` package; new env gates (`BRAIN2_LIVING_DOCS`, `BRAIN2_AUTO_CAPTURE`, `BRAIN2_AUTO_CAPTURE`-interval, `BRAIN2_LIVING_DOCS_LLM`, debounce N/T); new MCP tools (`brain2_note`, `brain2_notes_policy_{get,set}`, `brain2_distill`); new skills (`/brain2:notes`, `/brain2:docs`); new hooks (`Stop` session-note, `SessionStart` auto-capture, `SessionEnd` stop). Note `category="note"` Findings and the `.brain2/` git-ignored on-disk layout.

**Step 2: Commit**

```bash
git add CLAUDE.md docs/plans/2026-06-03-living-docs-design.md
git commit -m "docs(livingdocs): document Living Docs feature + status"
```

---

## Build order summary (dependency-correct)

1. **0.1, 0.2** config + skeleton
2. **1.1** paths
3. **6.1** state + `should_distill` (defines `schedule_distill` home)
4. **2.1** policy → **2.2** notes → **6.2** distill (`schedule_distill`) → **2.3** `brain2_note` tool + Stop hook
5. **3.1, 3.2** policy tools + `/brain2:notes` + wizard
6. **4.1, 4.2** watcher + SessionStart/End wiring
7. **5.1** fallback distiller
8. **6.3** distill integration test
9. **7.1, 7.2** `brain2_distill` + `/brain2:docs`
10. **8.1, 8.2** full suite green + docs

Each task: write failing test → run (fails) → implement → run (passes) → commit. DRY, YAGNI, TDD, frequent commits.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-06-03-living-docs.md`. Two execution options:

1. **Subagent-Driven (this session)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Parallel Session (separate)** — open a new session in the worktree with superpowers:executing-plans, batch execution with checkpoints.

Which approach?
