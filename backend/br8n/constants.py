"""Cross-cutting constants shared by the store and feature layers.

Kept dependency-free so low-level modules (e.g. store/sqlite.py) can import it
without a cycle through the feature packages that also use it.
"""
from __future__ import annotations

# Reserved, repo-independent tenancy scope for the cross-project journal. Used as
# both the project and KB name; resolve_tenant(JOURNAL_SCOPE, JOURNAL_SCOPE)
# yields a stable, org-scoped journal KB that is never derived from a repo+branch.
JOURNAL_SCOPE = "__journal__"
