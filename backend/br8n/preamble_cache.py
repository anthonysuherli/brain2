"""Stdlib-only cache for the injected session preamble primer.

Keyed by (session_id, project, kb). Read on every UserPromptSubmit turn by
hooks/preamble-inject.py — so this module imports ONLY the standard library
(br8n/__init__.py is empty, so `import br8n.preamble_cache` stays ~ms and never
pulls the heavy engine). Written on a cache miss; invalidated by a capture.

Every function is best-effort and never raises: a corrupt/missing file reads as a
miss, write/invalidate/prune failures are swallowed. The cache never breaks a turn.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


def _dir() -> Path:
    override = os.environ.get("BR8N_PREAMBLE_CACHE_DIR")
    return Path(override) if override else Path.home() / ".br8n" / "preamble-cache"


def cache_key(project: str, kb: str) -> str:
    """Stable 16-hex key for a (project, kb) pair."""
    return hashlib.sha256(f"{project}\0{kb}".encode()).hexdigest()[:16]


def _slug(s: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in s) or "default"


def _path(session_id: str, project: str, kb: str) -> Path:
    return _dir() / f"{cache_key(project, kb)}.{_slug(session_id)}.json"


def read(session_id: str, project: str, kb: str) -> str | None:
    """Return the cached primer string, or None if missing/unreadable/malformed."""
    try:
        data = json.loads(_path(session_id, project, kb).read_text())
        primer = data.get("primer")
        return primer if isinstance(primer, str) and primer else None
    except Exception:  # noqa: BLE001 — any miss/corruption → cache miss
        return None


def write(session_id: str, project: str, kb: str, primer: str) -> None:
    """Best-effort write of the primer, then prune old files. Never raises."""
    try:
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        _path(session_id, project, kb).write_text(
            json.dumps({"built_at": time.time(), "primer": primer})
        )
        prune()
    except Exception:  # noqa: BLE001 — cache write is best-effort
        pass


def invalidate(project: str, kb: str) -> None:
    """Delete the cached primer for (project, kb) across all sessions. Never raises."""
    try:
        prefix = cache_key(project, kb)
        for f in _dir().glob(f"{prefix}.*.json"):
            try:
                f.unlink()
            except OSError:
                pass
    except Exception:  # noqa: BLE001 — best-effort
        pass


def prune(max_age_hours: float = 24.0) -> None:
    """Best-effort removal of cache files older than max_age_hours. Never raises."""
    try:
        cutoff = time.time() - max_age_hours * 3600
        for f in _dir().glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass
