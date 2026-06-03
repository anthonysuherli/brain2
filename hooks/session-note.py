"""brain2 Stop hook — session-end note writer.

    python hooks/session-note.py

Reads the hook input JSON from stdin (provided by the Claude Code harness) at the
END of a conversation, derives the repo's project/kb from cwd, and emits a
non-blocking ``additionalContext`` directive telling Claude to summarize THIS
session into a note (per the KB's note policy) and persist it via
``mcp__brain2__brain2_note``. The actual summary + tool calls are Claude's work;
this hook only emits the directive text.

Design goals
------------
* **Non-blocking.** The directive is best-effort and tells Claude to skip silently
  if nothing substantive happened — it never blocks session end.
* **Fail-safe.** Any unexpected error (malformed stdin, not a git repo, gate off)
  causes a silent exit — this hook must never crash Claude Code.
* **Importable for testing.** Logic lives in ``build_note_directive``;
  ``main()`` is thin glue. ``repo_identity``/``derive_project_kb`` are reused from
  the SessionStart hook so cwd→project/kb derivation stays identical.
"""

from __future__ import annotations

import json
import os
import sys

# Reuse the exact cwd→project/kb derivation from the SessionStart hook so both
# hooks resolve the same target for the same repo.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "brain2_first_run_init",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "first-run-init.py"),
)
_fri = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_fri)
repo_identity = _fri.repo_identity
derive_project_kb = _fri.derive_project_kb


# ---------------------------------------------------------------------------
# Public helpers (importable for tests)
# ---------------------------------------------------------------------------


def build_note_directive(project: str, kb: str) -> str:
    """Return the additionalContext directive that drives end-of-session note-writing.

    Non-blocking by construction: it tells Claude to skip silently if nothing
    substantive happened, otherwise to summarize THIS conversation per the KB's note
    policy and persist it via ``brain2_note``. See skills/_shared/session-note.md."""
    return (
        f"brain2 session-end note for project '{project}' (kb='{kb}'). "
        "The conversation is ending — capture a durable session note (non-blocking, "
        "best-effort; see skills/_shared/session-note.md).\n\n"
        "Instructions:\n"
        "1. If nothing substantive happened this session (no decisions, no code "
        "changes, trivial Q&A), skip silently — do nothing.\n"
        "2. Resolve the target: project = git repo basename, kb = git branch, "
        "project_path = repo root (`git rev-parse --show-toplevel`). "
        f"For this session: project='{project}', kb='{kb}'.\n"
        "3. Fetch the KB's note policy: call "
        "mcp__brain2__brain2_notes_policy_get(project, kb, project_path) for the note "
        "template (sections) and steer. If unavailable, use a sensible default "
        "(Decisions / Changes / Open questions).\n"
        "4. Summarize THIS conversation into those sections, honoring the steer — "
        "concise, durable facts only (decisions made, what changed, open threads), "
        "not a transcript.\n"
        "5. Persist it: call mcp__brain2__brain2_note(project, kb, project_path, "
        "content, session_id, title) where content is the rendered markdown, title is "
        "a one-line summary, and session_id is this session's id.\n"
        "Do not block; this is fire-and-forget at session end."
    )


# ---------------------------------------------------------------------------
# Hook entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Stop hook entry point.

    Reads the hook context JSON from stdin (provided by the Claude Code harness),
    derives the repo's project/kb from cwd, and prints
    ``{"additionalContext": "..."}`` so the harness injects the note directive.
    Exits silently on a disabled gate, non-git cwd, or any error.
    """
    if os.getenv("BRAIN2_LIVING_DOCS", "1") == "0":
        return
    try:
        raw = sys.stdin.read()
        ctx = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 — malformed input → silent exit
        return

    cwd: str = (
        ctx.get("cwd")
        or (ctx.get("session") or {}).get("cwd")
        or os.getcwd()
    )

    # Not a git repo → not a brain2 target.
    if repo_identity(cwd) is None:
        return

    try:
        project, kb = derive_project_kb(cwd)
        print(json.dumps({"additionalContext": build_note_directive(project, kb)}))
    except Exception:  # noqa: BLE001 — any failure → stay silent
        return


if __name__ == "__main__":
    main()
