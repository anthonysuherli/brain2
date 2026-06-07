"""Resolve and bootstrap the on-disk .br8n/ Living Docs layout."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from br8n.config import get_config


def _safe(segment: str) -> str:
    """Filesystem-safe single path segment (branch names contain '/')."""
    return re.sub(r"[^A-Za-z0-9._-]+", "__", segment.strip()) or "default"


@dataclass(frozen=True)
class DocPaths:
    project_path: str
    kb: str

    @property
    def _cfg(self):
        return get_config().living_docs

    @property
    def root(self) -> Path:
        return Path(self.project_path) / self._cfg.root_dirname

    @property
    def notes_dir(self) -> Path:
        return self.root / self._cfg.notes_dirname / _safe(self.kb)

    @property
    def docs_dir(self) -> Path:
        return self.root / self._cfg.docs_dirname

    @property
    def timeline_dir(self) -> Path:
        return self.root / self._cfg.timeline_dirname

    @property
    def timeline_state_path(self) -> Path:
        return self.root / self._cfg.timeline_state_filename

    @property
    def policy_path(self) -> Path:
        return self.root / self._cfg.policy_filename

    @property
    def state_path(self) -> Path:
        return self.root / self._cfg.state_filename


def ensure_layout(paths: DocPaths) -> None:
    """Create dirs + a self-ignoring .gitignore (`*`) so .br8n/ is never committed."""
    paths.notes_dir.mkdir(parents=True, exist_ok=True)
    paths.docs_dir.mkdir(parents=True, exist_ok=True)
    gi = paths.root / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n")
