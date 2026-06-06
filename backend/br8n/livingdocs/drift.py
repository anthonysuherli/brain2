"""Canonical work-drift calculation — shared by the auto-capture watcher.

"Drift" is how far the working tree has moved from the **last captured snapshot**:

  * ``moved``   — symmetric difference between the tracked files the snapshot recorded
                  (parsed from its ``**Git diff stat**`` block) and the tracked files
                  changed *now* (``git diff HEAD --name-only``).
  * ``commits`` — commits on HEAD strictly after the snapshot's timestamp.

A repo is **drifted** when ``moved >= DRIFT_FILES_WARN`` OR ``commits >= 1`` — the exact
threshold the statusline renders. The watcher imports this module; the statusline
(``scripts/br8n-statusline.py``) is a zero-dependency script that keeps an in-sync
copy of the same constant + algorithm. Keep the two in lockstep.

NOTE: this is *work* drift (snapshot staleness). It is unrelated to
``br8n.knowledge_graph.drift`` (KG-schema drift).

Untracked files are intentionally excluded: a captured snapshot never records them, so
counting them would make drift perpetually non-empty (the bug that left the statusline
stuck at "drifted").
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone

# Same threshold the statusline uses — keep in sync with scripts/br8n-statusline.py.
DRIFT_FILES_WARN = 2

_DIFF_BLOCK_RE = re.compile(r"\*\*Git diff stat\*\*:\s*```[^\n]*\n(.*?)```", re.DOTALL)
_DIFF_PATH_RE = re.compile(r"^\s+(.+?)\s+\|")  # " path/to/file.py | N ±"
_HYP_RE = re.compile(r"\*\*Hypothesis\*\*:\s*(.+)", re.IGNORECASE)


def parse_diff_stat_block(content: str | None) -> set[str]:
    """Return the set of file paths from a snapshot's ``**Git diff stat**`` block."""
    if not content:
        return set()
    m = _DIFF_BLOCK_RE.search(content)
    if not m:
        return set()
    paths: set[str] = set()
    for line in m.group(1).splitlines():
        pm = _DIFF_PATH_RE.match(line)
        if pm:
            paths.add(pm.group(1).strip())
    return paths


def extract_hypothesis(content: str | None) -> str | None:
    """Pull the leading ``**Hypothesis**:`` line from a snapshot's content, or None."""
    if not content:
        return None
    m = _HYP_RE.search(content)
    return m.group(1).strip() if m else None


def _git(cwd: str, *args: str) -> str | None:
    """Best-effort ``git <args>`` → stripped stdout, or None on any failure."""
    try:
        res = subprocess.run(
            ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5
        )
    except Exception:  # noqa: BLE001 — subprocess/timeout/git-missing all best-effort
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def tracked_changed_files(cwd: str) -> set[str]:
    """Tracked files changed vs HEAD (staged + unstaged); untracked excluded.

    Mirrors the statusline's ``live_diff_files`` so the two agree on the live set.
    """
    raw = _git(cwd, "diff", "HEAD", "--name-only")
    if not raw:
        return set()
    return {line.strip() for line in raw.splitlines() if line.strip()}


def commits_since(cwd: str, captured_at: str) -> int:
    """Number of commits on HEAD strictly after ``captured_at`` (ISO 8601)."""
    raw = _git(cwd, "log", "--format=%aI")
    if not raw:
        return 0
    try:
        dt_captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return 0
    if dt_captured.tzinfo is None:
        dt_captured = dt_captured.replace(tzinfo=timezone.utc)
    count = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            dt_commit = datetime.fromisoformat(line)
            if dt_commit.tzinfo is None:
                dt_commit = dt_commit.replace(tzinfo=timezone.utc)
            if dt_commit > dt_captured:
                count += 1
        except Exception:  # noqa: BLE001
            pass
    return count


def compute_moved(captured_files: set[str], current_files: set[str]) -> int:
    """Count of files that entered or left the tracked-changed set since capture."""
    return len(captured_files.symmetric_difference(current_files))


def is_drifted(moved: int, commits: int) -> bool:
    """The single drift verdict: a commit, or >= DRIFT_FILES_WARN files moved."""
    return commits >= 1 or moved >= DRIFT_FILES_WARN
