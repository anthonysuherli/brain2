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
    # The harness sends session_id on every UserPromptSubmit; "default" is a graceful
    # fallback if it's ever absent (such turns share one cache slot — staler, never wrong).
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
