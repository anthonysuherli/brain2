"""brain2 SessionEnd hook — stop the Living Docs auto-capture watcher.

    python hooks/auto-capture-stop.py

Reads the hook input JSON from stdin, derives cwd, and signals the running watcher
(launched by ``auto-capture.py`` at SessionStart) to exit at its next tick by
writing its stop-file. Best-effort and silent: any error → silent return, so
session end is never blocked.
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import sys

# auto-capture.py lives alongside this script but isn't a package — load by path.
_spec = _ilu.spec_from_file_location(
    "brain2_auto_capture",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto-capture.py"),
)
_ac = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_ac)
stop_watcher = _ac.stop_watcher


def main() -> None:
    """SessionEnd entry point — signal the watcher to stop. Silent on any error."""
    try:
        raw = sys.stdin.read()
        ctx = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 — malformed input → silent exit
        ctx = {}
    cwd = ctx.get("cwd") or (ctx.get("session") or {}).get("cwd") or os.getcwd()
    try:
        stop_watcher(cwd)
    except Exception:  # noqa: BLE001 — best-effort; never crash session end
        return


if __name__ == "__main__":
    main()
