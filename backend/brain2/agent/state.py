"""Shared types for tool dispatch (adapted from Divergence; chat types removed)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TenantContext:
    """Resolved tenancy for the current request."""

    user_id: str
    org_id: str
    project_id: str
    kb_id: str
    thread_id: str
    access_token: str


@dataclass
class StreamEvent:
    """Event emitted by the exploration tool pipeline."""

    type: Literal["phase", "tool_call", "tool_result", "error", "done"]
    payload: dict[str, Any] = field(default_factory=dict)
