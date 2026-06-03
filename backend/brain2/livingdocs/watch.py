"""Living Docs auto-capture watcher — a non-LLM, change-driven background poll.

Runs as a detached subprocess (the launching hook is a separate task). On each
tick it reads cheap git state, fingerprints it, and persists a snapshot ONLY when
something meaningful changed since the last capture. Auto-captures are
DETERMINISTIC: ``trigger="idle"`` and no hypothesis — they reuse the exact capture
sequence the MCP ``brain2_capture`` tool uses
(``resolve_tenant`` → ``persist_snapshot`` → ``schedule_activity_update``).

Best-effort and non-blocking by design: a bad tick (git error, capture failure)
is logged and swallowed so the watcher keeps polling.

Gates (env, default on; ``"0"`` disables):
  * ``BRAIN2_LIVING_DOCS`` — Living Docs master gate.
  * ``BRAIN2_AUTO_CAPTURE`` — this watcher specifically.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
import time
from datetime import datetime, timezone

from brain2.capture.models import WorkspaceSnapshot
from brain2.capture.service import persist_snapshot
from brain2.config import get_config
from brain2.interfaces.mcp.tenancy import resolve_tenant
from brain2.knowledge_graph.activity import schedule_activity_update

logger = logging.getLogger(__name__)


def fingerprint(*, branch: str | None, diff_stat: str | None, open_files: list[str] | None) -> str:
    """Stable hash of the meaningful work state.

    Order-independent for ``open_files`` (sorted), so editor tab reordering alone
    never reads as a change.
    """
    normalized = (branch or "", diff_stat or "", tuple(sorted(open_files or [])))
    return hashlib.sha256(repr(normalized).encode("utf-8")).hexdigest()


def changed(prev: str | None, cur: str) -> bool:
    """True when the fingerprint moved (first tick — ``prev is None`` — is a change)."""
    return prev != cur


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
    diff_stat = _git(["diff", "--stat"], cwd)
    if diff_stat is None:
        return {}
    return {"branch": branch, "diff_stat": diff_stat, "open_files": []}


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
) -> str | None:
    """Persist one deterministic snapshot via the real capture sequence.

    Mirrors ``brain2_capture``: resolve_tenant → persist_snapshot →
    schedule_activity_update. Best-effort: logs and returns None on any error.
    """
    try:
        snap = WorkspaceSnapshot(
            project_path=project_path,
            trigger="idle",
            captured_at=datetime.now(timezone.utc).isoformat(),
            branch=branch,
            git_diff_stat=diff_stat,
            open_files=open_files,
            hypothesis=None,
        )
        ctx = resolve_tenant(project, kb, create=True)
        finding_id = await persist_snapshot(ctx, snap)
        schedule_activity_update(snap, finding_id)  # fire-and-forget; best-effort
        return finding_id
    except Exception:
        logger.exception("auto-capture failed for %s/%s", project, kb)
        return None


def run_watch(
    cwd: str,
    *,
    interval: int | None = None,
    stop_path: str | None = None,
    max_ticks: int | None = None,
) -> None:
    """Poll git state and auto-capture on change.

    Stops when ``stop_path`` exists (the hook's stop signal) or after ``max_ticks``
    ticks (testing only). The loop body is fully guarded so one bad tick never
    kills the watcher.
    """
    if os.getenv("BRAIN2_LIVING_DOCS", "1") == "0" or os.getenv("BRAIN2_AUTO_CAPTURE", "1") == "0":
        return

    if interval is None:
        interval = get_config().living_docs.watch_interval_seconds

    project, kb = derive_project_kb(cwd)
    project_path = cwd
    prev_fp: str | None = None
    ticks = 0

    while True:
        if stop_path and os.path.exists(stop_path):
            break
        try:
            state = read_git_state(cwd)
            if state:
                fp = fingerprint(
                    branch=state["branch"],
                    diff_stat=state["diff_stat"],
                    open_files=state["open_files"],
                )
                if changed(prev_fp, fp):
                    asyncio.run(
                        capture_once(
                            project,
                            kb,
                            project_path,
                            state["branch"],
                            state["diff_stat"],
                            state["open_files"],
                        )
                    )
                    prev_fp = fp
        except Exception:
            logger.exception("watch tick failed")

        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        time.sleep(interval)


if __name__ == "__main__":
    _cwd = os.getenv("BRAIN2_WATCH_CWD", os.getcwd())
    _stop = os.getenv("BRAIN2_WATCH_STOP")
    run_watch(_cwd, stop_path=_stop)
