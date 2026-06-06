"""Living Docs commit-boundary auto-capture — a non-LLM, drift-triggered re-anchor.

Invoked once per git commit by the ``post-commit`` hook (installed by
``hooks/auto-capture.py`` at SessionStart) as ``python -m br8n.livingdocs.watch
--once``. It reads cheap git state and computes **drift vs the last persisted
snapshot** using the shared ``br8n.livingdocs.drift`` module (the same threshold
the statusline renders). It persists a snapshot only when the repo has actually
**drifted** — ``moved >= DRIFT_FILES_WARN`` OR ``commits >= 1`` — or when there is
no prior snapshot (first anchor). A commit makes ``commits_since >= 1``, so it
re-anchors on every commit. Each capture resets the baseline, so the cadence is
self-bounded (no tiny near-duplicate snapshots).

There is **no continuous background watcher** — snapshots are taken only on commit
and on demand via ``/br8n:capture``.

Auto-captures **carry forward the last hypothesis** (intent persists across small
drifts) and use ``trigger="idle"``. They reuse the exact capture sequence the MCP
``br8n_capture`` tool uses
(``resolve_tenant`` → ``persist_snapshot`` → ``schedule_activity_update``).

Best-effort and non-blocking by design: a failed capture is logged and swallowed so
a commit never fails on our hook.

Gates (env, default on; ``"0"`` disables):
  * ``BR8N_LIVING_DOCS`` — Living Docs master gate.
  * ``BR8N_AUTO_CAPTURE`` — commit-boundary auto-capture specifically.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone

from br8n.capture.models import WorkspaceSnapshot
from br8n.capture.service import persist_snapshot
from br8n.interfaces.mcp.tenancy import resolve_tenant
from br8n.knowledge_graph.activity import schedule_activity_update
from br8n.livingdocs import drift
from br8n.store import get_store

logger = logging.getLogger(__name__)


def _git(args: list[str], cwd: str) -> str | None:
    """Best-effort `git <args>` → stripped stdout, or None on any failure."""
    try:
        res = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5
        )
    except Exception:  # subprocess error, timeout, git missing — all best-effort
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def read_git_state(cwd: str) -> dict:
    """Read cheap git state for a fingerprint. Returns ``{}`` on any failure.

    ``open_files`` isn't reliably available outside an editor → always empty here.
    Callers treat an empty dict as "skip this tick".
    """
    branch = _git(["branch", "--show-current"], cwd)
    if branch is None:
        return {}
    # `git diff HEAD --stat` (staged + unstaged tracked) matches the scope the drift
    # module's `tracked_changed_files` reads, so a snapshot self-resets drift to 0.
    diff_stat = _git(["diff", "HEAD", "--stat"], cwd)
    if diff_stat is None:
        return {}
    return {"branch": branch, "diff_stat": diff_stat, "open_files": []}


def last_snapshot(project: str, kb: str) -> dict | None:
    """Latest snapshot for ``(project, kb)`` → ``{content, created_at, hypothesis}``.

    Sync, best-effort: returns ``None`` when the KB doesn't exist yet, is empty, or
    on any backend error (callers treat ``None`` as "no prior anchor → capture").
    """
    try:
        ctx = resolve_tenant(project, kb, create=False)
        store = get_store(ctx.access_token, org_id=ctx.org_id)
        res = store.list_findings(ctx.kb_id, category="snapshot", limit=1)
        findings = (res or {}).get("findings") or []
        if not findings:
            return None
        # list_findings omits `content` (matches SupabaseStore) — fetch the full row.
        full = store.get_finding(ctx.kb_id, findings[0]["id"]) or {}
        content = full.get("content")
        return {
            "content": content,
            "created_at": findings[0].get("created_at") or full.get("created_at") or "",
            "hypothesis": drift.extract_hypothesis(content),
        }
    except Exception:  # noqa: BLE001 — KB-not-found or backend error → no anchor
        return None


def derive_project_kb(cwd: str) -> tuple[str, str]:
    """(project, kb) for ``cwd`` — repo-root basename + current branch.

    Best-effort: project falls back to the basename of ``cwd``; kb to ``"main"``.
    """
    toplevel = _git(["rev-parse", "--show-toplevel"], cwd)
    project = os.path.basename(toplevel) if toplevel else os.path.basename(os.path.abspath(cwd))
    branch = _git(["branch", "--show-current"], cwd)
    kb = branch or "main"
    return project, kb


async def capture_once(
    project: str,
    kb: str,
    project_path: str,
    branch: str | None,
    diff_stat: str | None,
    open_files: list[str],
    hypothesis: str | None = None,
) -> str | None:
    """Persist one snapshot via the real capture sequence.

    Mirrors ``br8n_capture``: resolve_tenant → persist_snapshot →
    schedule_activity_update. ``hypothesis`` is the carried-forward intent (the most
    recent hypothesis for this repo+branch), or None for the first anchor. Best-effort:
    logs and returns None on any error.
    """
    try:
        snap = WorkspaceSnapshot(
            project_path=project_path,
            trigger="idle",
            captured_at=datetime.now(timezone.utc).isoformat(),
            branch=branch,
            git_diff_stat=diff_stat,
            open_files=open_files,
            hypothesis=hypothesis,
        )
        ctx = resolve_tenant(project, kb, create=True)
        finding_id = await persist_snapshot(ctx, snap)
        schedule_activity_update(snap, finding_id)  # fire-and-forget; best-effort
        return finding_id
    except Exception:
        logger.exception("auto-capture failed for %s/%s", project, kb)
        return None


def should_capture(cwd: str, project: str, kb: str) -> tuple[bool, str | None]:
    """Decide whether to auto-capture now + the hypothesis to carry forward.

    * No prior snapshot → ``(True, None)`` — first anchor.
    * Drifted vs the last snapshot (``drift.is_drifted``) → ``(True, last_hypothesis)``.
    * Otherwise → ``(False, None)``.

    Best-effort: any error → ``(False, None)`` (skip this tick).
    """
    try:
        last = last_snapshot(project, kb)
        if last is None:
            return True, None
        captured_files = drift.parse_diff_stat_block(last["content"])
        current_files = drift.tracked_changed_files(cwd)
        moved = drift.compute_moved(captured_files, current_files)
        commits = drift.commits_since(cwd, last["created_at"])
        if drift.is_drifted(moved, commits):
            return True, last["hypothesis"]
        return False, None
    except Exception:  # noqa: BLE001 — best-effort; never break the watch loop
        return False, None


def run_once(cwd: str) -> str | None:
    """One-shot drift-triggered capture — used by the ``post-commit`` git hook.

    A commit makes ``commits_since`` >= 1, so this re-anchors immediately on commit
    (the strongest drift signal). Gated + best-effort: returns None when disabled,
    not drifted, or on any error.
    """
    if os.getenv("BR8N_LIVING_DOCS", "1") == "0" or os.getenv("BR8N_AUTO_CAPTURE", "1") == "0":
        return None
    try:
        project, kb = derive_project_kb(cwd)
        state = read_git_state(cwd)
        if not state:
            return None
        capture, hyp = should_capture(cwd, project, kb)
        if not capture:
            return None
        return asyncio.run(
            capture_once(
                project, kb, cwd, state["branch"], state["diff_stat"],
                state["open_files"], hypothesis=hyp,
            )
        )
    except Exception:  # noqa: BLE001 — best-effort; a commit must never fail on our hook
        logger.exception("run_once failed for %s", cwd)
        return None


if __name__ == "__main__":
    # Only entry point: the post-commit hook's `-m br8n.livingdocs.watch --once`.
    run_once(os.getenv("BR8N_WATCH_CWD", os.getcwd()))
