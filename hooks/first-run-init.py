"""brain2 SessionStart hook — first-run init + schema-offer guard.

    python hooks/first-run-init.py

Reads the hook input JSON from stdin (provided by the Claude Code harness),
determines whether this repo already has a brain2 KB, and either:
  * **No KB** → emits a first-run directive (seed the KB + offer the schema wizard).
  * **KB exists** → asks the drift detector whether to surface a KG-schema offer
    *now* (cold-start or drift); emits a one-line, debounced, non-blocking offer
    only when warranted — otherwise stays completely silent.
  * Exits silently otherwise (not a git repo, or backend unreachable).

This is the turn-boundary **surfacing** path for the self-maintaining KB's one
human seam: capture/distill/graph-population happen in the background; the schema
is the only thing brain2 taps the user about, and only when the detector says so.

Design goals
------------
* **Fail-safe.** Any unexpected error causes a silent exit — this hook must
  never crash Claude Code's session start.
* **Fail-closed on backend outage.** If brain2's store is unreachable for
  reasons other than "not found", we treat it as uncertain and exit without
  emitting a directive.  We would rather skip the offer than spam it.
* **Importable for testing.** All logic lives in module-level functions
  (``repo_identity``, ``derive_project_kb``, ``build_directive``,
  ``check_kb_exists``).  ``main()`` is thin glue.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys


# ---------------------------------------------------------------------------
# Public helpers (importable for tests)
# ---------------------------------------------------------------------------


def repo_identity(cwd: str) -> str | None:
    """Return a normalized repo identity string, or None if not a git repo.

    Algorithm
    ---------
    1. ``git remote get-url origin`` — strip scheme, auth, and ``.git`` suffix,
       then lowercase.  Example: ``git@github.com:user/repo.git``
       → ``github.com/user/repo``.
    2. Fallback: ``git rev-parse --show-toplevel`` — use the repo root path.
    3. Return ``None`` if ``git`` exits non-zero (not a git repo or no git).
    """
    # Attempt 1 — remote origin URL.
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            return _normalize_remote_url(url)
    except Exception:  # noqa: BLE001 — subprocess failure is non-fatal
        pass

    # Attempt 2 — repo root path.
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:  # noqa: BLE001
        pass

    return None


def _normalize_remote_url(url: str) -> str:
    """Strip scheme, auth credentials, and ``.git`` suffix; lowercase.

    Handles HTTPS (``https://user:pass@host/path``) and SSH
    (``git@host:user/repo.git`` or ``ssh://git@host/user/repo.git``).
    """
    url = url.strip()

    # SSH shorthand: git@github.com:user/repo.git
    ssh_shorthand = re.match(r"^[a-zA-Z0-9_.-]+@([^:]+):(.+)$", url)
    if ssh_shorthand:
        host, path = ssh_shorthand.group(1), ssh_shorthand.group(2)
        path = path.removesuffix(".git")
        return f"{host}/{path}".lower()

    # Strip scheme (https://, ssh://, git://, …)
    without_scheme = re.sub(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://", "", url)
    # Strip auth (user:pass@)
    without_auth = re.sub(r"^[^@]*@", "", without_scheme)
    # Strip .git suffix
    without_git = without_auth.removesuffix(".git")
    return without_git.lower()


def derive_project_kb(cwd: str) -> tuple[str, str]:
    """Derive ``(project_name, kb_name)`` from the repo identity or cwd.

    ``project`` is the repo's basename — the last path component, with
    special characters replaced by hyphens and leading/trailing hyphens
    stripped.  ``kb`` is always ``"main"`` (the repo-level session KB).
    """
    identity = repo_identity(cwd)
    if identity:
        base = identity.rstrip("/").rsplit("/", 1)[-1]
    else:
        base = os.path.basename(os.path.abspath(cwd))

    # Clean: keep alphanumerics and hyphens only.
    cleaned = re.sub(r"[^a-zA-Z0-9-]", "-", base).strip("-") or "repo"
    return cleaned, "main"


def build_directive(project: str, kb: str) -> str:
    """Return the additionalContext directive string injected on first-run.

    The directive instructs Claude to:
    1. Print one visible line so the user knows init is happening.
    2. Dispatch a background init subagent (``skills/_shared/project-init.md``).
    3. After the subagent completes, offer the KG schema wizard once
       (``skills/_shared/kg-schema-wizard.md``).
    """
    return (
        f"brain2 first-run detected for project '{project}' (kb='{kb}'). "
        "This is a new repo with no brain2 KB yet.\n\n"
        "Instructions:\n"
        "1. Print exactly one line to the user: "
        "\"Initializing brain2 for this repo in the background…\"\n"
        "2. Immediately dispatch a background subagent following the instructions in "
        "skills/_shared/project-init.md to seed the brain2 KB for this repo. "
        f"Pass project='{project}', kb='{kb}' to every brain2 MCP call. "
        "Do not wait for the subagent — return control to the user right away.\n"
        "3. When the background subagent completes and signals draft_ready=true, "
        "offer the KG schema wizard to the user exactly once by following "
        "skills/_shared/kg-schema-wizard.md. "
        "After the offer is surfaced call mcp__brain2__brain2_mark_init_offered "
        f"with project='{project}' and kb='{kb}' so this offer is not repeated.\n"
        "Do not block the user's current session during any of the above steps."
    )


def check_kb_exists(project: str, kb: str) -> bool | None:
    """Ask the brain2 backend whether a KB already exists.

    Returns
    -------
    True   — KB exists (do NOT emit the directive).
    False  — KB does not exist (DO emit the directive).
    None   — backend is unreachable or another error occurred (fail-closed:
             treat as uncertain, do NOT emit the directive).
    """

    async def _check() -> bool:
        # Import brain2 directly — the hook runs inside the same venv.
        from brain2.interfaces.mcp.tenancy import resolve_tenant  # noqa: PLC0415

        resolve_tenant(project, kb, create=False)
        return True

    try:
        return asyncio.run(_check())
    except RuntimeError as exc:
        if "not found" in str(exc).lower():
            return False
        # Genuine backend error — fail closed.
        return None
    except Exception:  # noqa: BLE001 — any other failure = uncertain
        return None


def pending_schema_offer(project: str, kb: str) -> dict | None:
    """Best-effort: should brain2 surface a KG-schema offer for an *existing* KB now?

    Mirrors the ``brain2_schema_drift`` MCP tool in-process (the hook shares the
    venv). Returns the verdict dict when the detector says to offer **now**
    (``should_offer`` and an actionable mode — ``drift`` or ``cold_start``), else
    ``None`` — so a session with no drift stays completely silent: no context
    injected, no work for Claude.

    Fail-closed: a disabled ``BRAIN2_SCHEMA_DRIFT`` gate, an unreachable backend, an
    unbuilt graph, or any error all yield ``None``. Must never crash session start.
    """
    if os.getenv("BRAIN2_SCHEMA_DRIFT", "1") == "0":
        return None
    try:
        from brain2.config import get_config  # noqa: PLC0415
        from brain2.interfaces.mcp.tenancy import resolve_tenant  # noqa: PLC0415
        from brain2.knowledge_graph.drift import assess_drift  # noqa: PLC0415
        from brain2.store import get_store  # noqa: PLC0415

        ctx = resolve_tenant(project, kb, create=False)
        store = get_store(ctx.access_token, org_id=ctx.org_id)
        verdict = assess_drift(
            store,
            ctx.kb_id,
            get_config().drift,
            init_offered=store.get_init_offered(ctx.kb_id),
            drift_marker=store.get_drift_marker(ctx.kb_id),
        )
    except Exception:  # noqa: BLE001 — best-effort; any failure → stay silent
        return None

    if verdict.should_offer and verdict.mode in ("drift", "cold_start"):
        return verdict.to_dict()
    return None


def build_offer_directive(project: str, kb: str, verdict: dict) -> str:
    """Return the additionalContext directive that surfaces a schema offer once.

    Non-blocking by construction: it tells Claude to print the one-line offer, stamp
    the debounce marker so it won't re-nag, and run ``/brain2:schema`` *only* if the
    user accepts. The stamp differs by mode — cold-start uses ``mark_init_offered``,
    drift uses ``mark_drift_offered`` (at the current residual count)."""
    mode = verdict.get("mode")
    offer = verdict.get("offer_line") or (
        f"brain2's knowledge graph for '{project}' may need a schema — `/brain2:schema`"
    )
    if mode == "cold_start":
        stamp = (
            "call mcp__brain2__brain2_mark_init_offered with "
            f"project='{project}', kb='{kb}'"
        )
    else:  # drift
        residual = int(verdict.get("residual") or 0)
        stamp = (
            "call mcp__brain2__brain2_mark_drift_offered with "
            f"project='{project}', kb='{kb}', residual={residual}"
        )
    return (
        f"brain2 schema offer ({mode}) for project '{project}' (kb='{kb}'). "
        "Its knowledge graph has accumulated entities the current ontology can't "
        "place.\n\n"
        "Instructions (non-blocking — surface once, do NOT interrupt the user's "
        "current task):\n"
        f'1. Print exactly one line to the user: "{offer}"\n'
        f"2. Immediately {stamp} so this offer is not repeated until warranted again.\n"
        "3. Only if the user accepts, run /brain2:schema (the guided KG-schema "
        "wizard). Otherwise carry on — do not block.\n"
        "Do not re-raise this offer yourself; the stamp in step 2 handles debouncing."
    )


# ---------------------------------------------------------------------------
# Hook entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """SessionStart hook entry point.

    Reads the hook context JSON from stdin (provided by the Claude Code
    harness).  The harness sends:
        {"session": {"cwd": "/absolute/path", ...}, ...}

    On first-run: prints ``{"additionalContext": "..."}`` to stdout so the
    harness injects the directive into Claude's context.
    On everything else: exits silently (no output).
    """
    try:
        raw = sys.stdin.read()
        ctx = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 — malformed input → silent exit
        return

    # Extract cwd from the hook payload.
    cwd: str = (
        ctx.get("cwd")
        or (ctx.get("session") or {}).get("cwd")
        or os.getcwd()
    )

    # Not a git repo → not a brain2 target.
    identity = repo_identity(cwd)
    if identity is None:
        return

    project, kb = derive_project_kb(cwd)

    exists = check_kb_exists(project, kb)
    if exists is True:
        # KB already exists — a normal session. Surface a KG-schema offer only if
        # the drift detector says so right now; otherwise stay silent.
        verdict = pending_schema_offer(project, kb)
        if verdict:
            print(json.dumps({"additionalContext": build_offer_directive(project, kb, verdict)}))
        return
    if exists is None:
        # Backend unreachable — fail closed, don't emit.
        return

    # exists is False → first run.  Emit the directive.
    directive = build_directive(project, kb)
    print(json.dumps({"additionalContext": directive}))


if __name__ == "__main__":
    main()
