"""br8n SessionStart hook — install the commit-boundary auto-capture hook.

    python hooks/auto-capture.py

Reads the hook input JSON from stdin (provided by the Claude Code harness) and,
when the repo is a br8n target and the Living Docs / auto-capture gates are on,
installs a best-effort ``post-commit`` git hook that re-anchors a snapshot on every
commit (via ``br8n.livingdocs.watch --once``). That commit hook + the on-demand
``/br8n:capture`` path are the only two ways snapshots are taken — there is no
longer a continuous background watcher polling the repo on a timer.

Design goals
------------
* **Fail-safe.** Any unexpected error → silent return. This hook must never crash
  Claude Code's session start.
* **Best-effort.** A failed install degrades to "no commit-boundary auto-capture
  this session"; the on-demand ``/br8n:capture`` path is unaffected.
* **Importable for testing.** Logic lives in ``should_install`` / ``_repo_root`` /
  ``install_post_commit_hook``; ``main`` is thin glue.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Reuse the exact cwd→repo derivation from the SessionStart guard so all hooks
# agree on what counts as a br8n target.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "br8n_first_run_init",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "first-run-init.py"),
)
_fri = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_fri)
repo_identity = _fri.repo_identity


# ---------------------------------------------------------------------------
# Public helpers (importable for tests)
# ---------------------------------------------------------------------------


def should_install(cwd: str) -> bool:
    """True iff the commit-boundary hook should be installed for ``cwd``.

    Requires both gates on (``BR8N_LIVING_DOCS`` master, ``BR8N_AUTO_CAPTURE``
    specific) AND ``cwd`` to be a git repo. Never raises — any error → False.
    """
    try:
        if os.getenv("BR8N_LIVING_DOCS", "1") == "0":
            return False
        if os.getenv("BR8N_AUTO_CAPTURE", "1") == "0":
            return False
        return repo_identity(cwd) is not None
    except Exception:  # noqa: BLE001 — gate check must never crash session start
        return False


def _repo_root(cwd: str) -> str:
    """Repo root via ``git rev-parse --show-toplevel``; fall back to ``cwd``."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return os.path.abspath(cwd)


_POST_COMMIT_MARKER = "# br8n-living-docs auto-capture (re-anchor on commit)"


def install_post_commit_hook(cwd: str, python_exe: str) -> bool:
    """Best-effort install of a ``post-commit`` hook that re-anchors a snapshot on commit.

    Marker-guarded (idempotent) and append-safe — never clobbers an existing hook;
    appends our line if one is already present. Uses ``git rev-parse --git-path hooks``
    so it resolves correctly for worktrees too. Returns True iff our line is present
    afterwards. Never raises.
    """
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return False
        hooks_dir = Path(res.stdout.strip())
        if not hooks_dir.is_absolute():
            hooks_dir = Path(cwd) / hooks_dir
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook = hooks_dir / "post-commit"

        line = (
            f'(BR8N_WATCH_CWD="$(git rev-parse --show-toplevel)" '
            f'"{python_exe}" -m br8n.livingdocs.watch --once >/dev/null 2>&1 &)  '
            f"{_POST_COMMIT_MARKER}\n"
        )
        if hook.exists():
            existing = hook.read_text()
            if _POST_COMMIT_MARKER in existing:
                return True  # idempotent
            sep = "" if existing.endswith("\n") else "\n"
            hook.write_text(existing + sep + line)
        else:
            hook.write_text("#!/bin/sh\n" + line)
        hook.chmod(0o755)
        return True
    except Exception:  # noqa: BLE001 — hook install is best-effort; never crash session start
        return False


def install(cwd: str) -> bool:
    """Install the commit-boundary auto-capture hook for ``cwd``.

    No-ops (returns False) when ``should_install`` is False. Otherwise installs the
    best-effort ``post-commit`` re-anchor hook and returns whether it's present.
    Best-effort: any error → False.
    """
    if not should_install(cwd):
        return False
    try:
        return install_post_commit_hook(_repo_root(cwd), sys.executable)
    except Exception:  # noqa: BLE001 — install failure must never crash the session
        return False


# ---------------------------------------------------------------------------
# Hook entry point
# ---------------------------------------------------------------------------


def _cwd_from_stdin() -> str:
    """Read the harness hook payload from stdin and extract cwd (fail-safe)."""
    try:
        raw = sys.stdin.read()
        ctx = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        ctx = {}
    return ctx.get("cwd") or (ctx.get("session") or {}).get("cwd") or os.getcwd()


def main() -> None:
    """SessionStart entry point — install the commit hook, emit nothing.

    Exits silently on any error or disabled gate. Produces no ``additionalContext``:
    installing a git hook is pure background work, so the user's session is untouched.
    """
    try:
        install(_cwd_from_stdin())
    except Exception:  # noqa: BLE001 — belt-and-suspenders; never crash session start
        return


if __name__ == "__main__":
    main()
