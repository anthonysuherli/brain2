"""Per-KB note-taking policy: section template + free-text steer.

Mirrors the load/save convention used elsewhere in livingdocs: default on a
missing or corrupt file, never raise. The policy lets the user dictate what kind
of session notes get taken — which sections are enabled plus a free-text steer.
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from br8n.livingdocs.paths import DocPaths, ensure_layout

_DEFAULT_SECTIONS = ["Decisions", "Changes", "Open Questions", "Next Steps"]


class NoteSection(BaseModel):
    name: str
    enabled: bool = True


class NotePolicy(BaseModel):
    sections: list[NoteSection]
    steer: str = ""


def default_policy() -> NotePolicy:
    return NotePolicy(sections=[NoteSection(name=n) for n in _DEFAULT_SECTIONS])


def load_policy(paths: DocPaths) -> NotePolicy:
    """Read the on-disk policy; return `default_policy()` on any failure."""
    try:
        raw = paths.policy_path.read_text()
    except (FileNotFoundError, OSError):
        return default_policy()
    try:
        return NotePolicy.model_validate_json(raw)
    except Exception:
        # Corrupt JSON or schema drift — fall back to default, never crash.
        return default_policy()


def save_policy(paths: DocPaths, policy: NotePolicy) -> None:
    """Persist the policy to disk, creating the layout if needed."""
    ensure_layout(paths)
    paths.policy_path.write_text(json.dumps(policy.model_dump(), indent=2) + "\n")
