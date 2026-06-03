"""brain2 SessionStart hook — launch the Living Docs auto-capture watcher.

    python hooks/auto-capture.py

Reads the hook input JSON from stdin (provided by the Claude Code harness) and,
when the repo is a brain2 target and the Living Docs / auto-capture gates are on,
launches the change-driven watcher (``brain2.livingdocs.watch``) as a DETACHED
subprocess that polls git state and auto-captures snapshots on change. The watcher
exits when its stop-file appears — written by the SessionEnd hook
(``auto-capture-stop.py``).

Routing
-------
Two scripts, one per event, wired separately in ``hooks.json`` (Claude Code routes
hooks per-event, so no runtime event-sniffing is needed):
  * ``auto-capture.py``      → SessionStart → ``main()``      → ``launch_watcher``
  * ``auto-capture-stop.py`` → SessionEnd   → ``stop_main()`` → ``stop_watcher``

No-double-launch + clean stop
-----------------------------
Per repo we keep two files under ``<repo_root>/.brain2/``:
  * ``.watch.stop`` — the watcher polls this each tick and exits when it appears.
  * ``.watch.pid``  — the most recently launched watcher's pid (diagnostics).
On launch we REMOVE any stale stop-file (so a fresh watcher won't immediately
exit) and the spawned watcher re-checks the gates itself, so a disabled gate
no-ops cheaply even if this hook somehow fires.

Design goals
------------
* **Fail-safe.** Any unexpected error → silent return. This hook must never crash
  Claude Code's session start.
* **Best-effort.** A failed spawn degrades to "no auto-capture this session";
  the on-demand ``/brain2:capture`` path is unaffected.
* **Importable for testing.** Logic lives in ``should_launch`` / ``paths_for`` /
  ``launch_watcher`` / ``stop_watcher``; ``main`` is thin glue.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Reuse the exact cwd→repo derivation from the SessionStart guard so all hooks
# agree on what counts as a brain2 target.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "brain2_first_run_init",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "first-run-init.py"),
)
_fri = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_fri)
repo_identity = _fri.repo_identity


# ---------------------------------------------------------------------------
# Public helpers (importable for tests)
# ---------------------------------------------------------------------------


def should_launch(cwd: str) -> bool:
    """True iff the watcher should be launched for ``cwd``.

    Requires both gates on (``BRAIN2_LIVING_DOCS`` master, ``BRAIN2_AUTO_CAPTURE``
    specific) AND ``cwd`` to be a git repo. Never raises — any error → False.
    """
    try:
        if os.getenv("BRAIN2_LIVING_DOCS", "1") == "0":
            return False
        if os.getenv("BRAIN2_AUTO_CAPTURE", "1") == "0":
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


def paths_for(cwd: str) -> tuple[str, str]:
    """Return ``(stop_file, pid_file)`` absolute paths under ``<repo_root>/.brain2/``.

    Ensures the ``.brain2`` directory exists (best-effort mkdir).
    """
    root = _repo_root(cwd)
    brain2_dir = Path(root) / ".brain2"
    try:
        brain2_dir.mkdir(parents=True, exist_ok=True)
        # Self-ignoring (`*`) so .brain2/ runtime files never pollute git — mirrors
        # brain2.livingdocs.paths.ensure_layout (kept local so the hook needs no
        # brain2 import for path bookkeeping).
        gi = brain2_dir / ".gitignore"
        if not gi.exists():
            gi.write_text("*\n")
    except Exception:  # noqa: BLE001 — dir creation is best-effort
        pass
    return str(brain2_dir / ".watch.stop"), str(brain2_dir / ".watch.pid")


_POST_COMMIT_MARKER = "# brain2-living-docs auto-capture (re-anchor on commit)"


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
            f'(BRAIN2_WATCH_CWD="$(git rev-parse --show-toplevel)" '
            f'"{python_exe}" -m brain2.livingdocs.watch --once >/dev/null 2>&1 &)  '
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


def launch_watcher(cwd: str) -> int | None:
    """Spawn the detached watcher for ``cwd``; return its pid (or None).

    No-ops (returns None) when ``should_launch`` is False. Otherwise installs the
    best-effort ``post-commit`` re-anchor hook, removes any stale stop-file, spawns
    ``python -m brain2.livingdocs.watch`` detached with the watcher's env contract,
    records the pid, and returns it. Best-effort: any error → None.
    """
    if not should_launch(cwd):
        return None
    try:
        root = _repo_root(cwd)
        stop_file, pid_file = paths_for(cwd)

        # Instant re-anchor on commit (the strongest drift signal), best-effort.
        install_post_commit_hook(root, sys.executable)

        # Clear a stale stop-file so the fresh watcher doesn't exit on tick 1.
        try:
            if os.path.exists(stop_file):
                os.remove(stop_file)
        except Exception:  # noqa: BLE001
            pass

        env = dict(os.environ)
        env["BRAIN2_WATCH_CWD"] = root
        env["BRAIN2_WATCH_STOP"] = stop_file

        proc = subprocess.Popen(
            [sys.executable, "-m", "brain2.livingdocs.watch"],
            env=env,
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            Path(pid_file).write_text(str(proc.pid))
        except Exception:  # noqa: BLE001 — pid-file is diagnostics only
            pass
        return proc.pid
    except Exception:  # noqa: BLE001 — spawn failure must never crash the session
        return None


def stop_watcher(cwd: str) -> None:
    """Signal the running watcher to exit by touching its stop-file. Never raises.

    Gate-independent: even if a gate was flipped off mid-session we still want to
    stop a watcher that an earlier (gated-on) start launched.
    """
    try:
        stop_file, _pid_file = paths_for(cwd)
        Path(stop_file).write_text("stop")
    except Exception:  # noqa: BLE001 — best-effort; session end must not crash
        return


# ---------------------------------------------------------------------------
# Hook entry points
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
    """SessionStart entry point — launch the watcher, emit nothing.

    Exits silently on any error or disabled gate. Produces no ``additionalContext``:
    the watcher is pure background work, so the user's session is untouched.
    """
    try:
        launch_watcher(_cwd_from_stdin())
    except Exception:  # noqa: BLE001 — belt-and-suspenders; never crash session start
        return


if __name__ == "__main__":
    main()
