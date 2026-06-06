# br8n — `/br8n:pickup`: resume card + cross-repo selector

**Date:** 2026-06-01
**Status:** Approved — ready to implement
**Supersedes:** the `/br8n:resume` skill (renamed to `/br8n:pickup`)

## Problem

Two things at once:

1. **Name confusion.** The br8n `resume` skill reads like Claude Code's built-in
   session `--resume`. Even though plugin skills are namespaced (`/br8n:resume`),
   the overlap is confusing. Rename to `pickup`.
2. **No cross-repo entry.** `/br8n:resume` only ever resumes the *current* git
   repo+branch. If you're not in a repo, or want to jump back into a different repo
   you've been capturing to, there's no path — and a `coverage='gap'` result is a
   dead-end. We already store everything needed (`Store.list_projects()`), but no
   MCP tool exposes it, so a skill can't reach it.

## Solution

Rename the skill to `pickup` and make it **arg-driven**: the bare fast path is
unchanged (resume here), but a no-match / explicit `list`/`pick` / repo-name arg
opens a **selector** over every repo+branch you've captured to.

### Trigger model (arg-driven)

| Invocation | Behavior |
|---|---|
| `/br8n:pickup` (in a git repo with captures) | Resolve `project`/`kb` from git → `br8n_resume` → render card. **Unchanged.** |
| `/br8n:pickup` with `coverage='gap'`, or not in a git repo, or arg = `list`/`pick` | **Selector mode** (see below). |
| `/br8n:pickup <name>` | `br8n_projects` → fuzzy-match name against project/kb. One match → resume it. Multiple → filtered selector. |

### Selector mode

Call `br8n_projects`, render most-recent-first, mark the current repo+branch:

```
Where do you want to pick up?
  1. br8n · dev        2h ago    12 snapshots   ← you are here
  2. br8n · main       1d ago     4 snapshots
  3. delapan · main   3d ago     9 snapshots
```

User picks a row (number or name) → `br8n_resume(project, kb)` → standard card.
Empty list → fall back to `/br8n:capture` (start tracking) or `/br8n:explore`.

## Backend changes

Only one new surface; no existing tool is renamed.

### 1. `br8n_projects` MCP tool — `interfaces/mcp/server.py`

```python
@mcp.tool()
async def br8n_projects() -> dict:
    """List every repo+branch you've captured to, most-recent first.

    Powers the /br8n:pickup selector: each project carries its branches
    with last_activity + snapshot_count chips. Org-scoped on cloud, the
    single local store on the free tier. Returns {projects: [...]}.
    """
    store = resolve_store()
    return {"projects": store.list_projects()}
```

Wraps the existing `Store.list_projects()` (already behind `/v1/projects`). Mirrors
`br8n_activity` as a no-target cross-repo MCP tool.

### 2. `resolve_store()` helper — `interfaces/mcp/tenancy.py`

The identity fork from `resolve_tenant`, minus project/kb binding:

```python
def resolve_store():
    """Org-scoped store with no project/kb binding (for cross-repo reads)."""
    from br8n.store import active_backend, get_store
    if active_backend() == "local":
        return get_store()
    _user_id, token = _login()
    return get_store(token)
```

Correct on both tiers; adds no new auth surface.

### 3. `br8n_resume` — unchanged

It stays the single-target tap. The skill is what gains the selector role.

## Skill / docs changes (rename `resume` → `pickup`)

- `skills/resume/` → `skills/pickup/`; frontmatter `name: resume` → `name: pickup`;
  rewrite body for the arg-driven trigger + selector mode.
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — skill entry.
- Cross-refs: `skills/capture/SKILL.md`, `skills/explore/SKILL.md`,
  `skills/activity/SKILL.md`, `skills/search/SKILL.md`,
  `skills/_shared/preamble-first.md` — `/br8n:resume` → `/br8n:pickup`.
- `CLAUDE.md` — Plugin skills table + tree.

## Out of scope (YAGNI)

- No new HTTP endpoint (`/v1/projects` already exists).
- No rename of the `br8n_resume` MCP tool.
- No fuzzy-ranking beyond simple substring match + most-recent ordering.
