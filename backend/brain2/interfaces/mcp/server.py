"""brain2 MCP server — capture + resume tools for Claude Code.

    python -m brain2.interfaces.mcp.server

Add to .claude/settings.json:

    {
      "mcpServers": {
        "brain2": {
          "command": "python",
          "args": ["-m", "brain2.interfaces.mcp.server"],
          "cwd": "/path/to/brain2/backend"
        }
      }
    }
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from brain2.agent.preamble import select_preamble
from brain2.capture.models import WorkspaceSnapshot
from brain2.capture.service import persist_snapshot
from brain2.config import get_config, get_settings
from brain2.exploration import run_exploration
from brain2.interfaces.mcp.banner import BRAIN2_BANNER
from brain2.interfaces.mcp.tenancy import resolve_tenant
from brain2.knowledge_graph.activity import query_activity, schedule_activity_update
from brain2.monitoring.recorder import PREAMBLE_TARGETS
from brain2.store import get_store

mcp = FastMCP("brain2")


@mcp.tool()
async def brain2_capture(
    project: str,
    kb: str,
    trigger: str,
    captured_at: str,
    branch: str | None = None,
    cursor_file: str | None = None,
    cursor_line: int | None = None,
    open_files: list[str] | None = None,
    git_diff_stat: str | None = None,
    terminal_tail: str | None = None,
    hypothesis: str | None = None,
    project_path: str = "",
) -> dict:
    """Persist a workspace snapshot as a Finding. Creates the project/KB on demand.

    Call this when the developer is interrupted (blur, git checkout, idle).
    `hypothesis` is the one-line intent string — the wedge that makes context
    recovery 3–5× faster. Returns the finding id.
    """
    snap = WorkspaceSnapshot(
        project_path=project_path or project,
        trigger=trigger,  # type: ignore[arg-type]
        captured_at=captured_at,
        branch=branch,
        git_diff_stat=git_diff_stat,
        open_files=open_files or [],
        cursor_file=cursor_file,
        cursor_line=cursor_line,
        terminal_tail=terminal_tail,
        hypothesis=hypothesis,
    )
    ctx = resolve_tenant(project, kb, create=True)
    finding_id = await persist_snapshot(ctx, snap)
    schedule_activity_update(snap, finding_id)  # fire-and-forget; best-effort
    return {"finding_id": finding_id, "project": project, "kb": kb}


@mcp.tool()
async def brain2_resume(
    project: str, kb: str, query: str | None = None, depth: str = "normal"
) -> dict:
    """Tap the session KB and return the 30-second resume card.

    Returns `{banner, preamble, coverage, project, kb}`.
    coverage routes behavior: rich → instant recall, gap → offer explore.
    """
    ctx = resolve_tenant(project, kb, create=False)
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    preamble, coverage = await select_preamble(query, store=store, kb_id=ctx.kb_id, depth=depth)
    await store.record_access(
        org_id=ctx.org_id,
        kb_id=ctx.kb_id,
        surface="mcp",
        targets=PREAMBLE_TARGETS,
        query_text=query,
    )
    return {
        "banner": BRAIN2_BANNER,
        "preamble": preamble,
        "coverage": coverage,
        "project": project,
        "kb": kb,
    }


@mcp.tool()
async def brain2_explore(
    project: str,
    kb: str,
    prompt: str,
    max_findings: int | None = None,
) -> dict:
    """Run the gap-fill explore pipeline (plan→search→crawl→extract→merge).

    Call this when `brain2_resume` returns coverage='gap'. Blocks until the
    pipeline completes (1–3 min). Persists findings to the KB and rebuilds
    the synopsis — the next `brain2_resume` call will be richer.
    Returns finding_count and finding_ids.
    """
    from brain2.agent.synopsis import schedule_rebuild
    from brain2.api.explore import _persist_findings

    ctx = resolve_tenant(project, kb, create=True)
    cfg = get_config().exploration
    max_f = min(max_findings or cfg.default_max_findings, cfg.max_findings)

    import uuid as _uuid
    exploration_id = str(_uuid.uuid4())

    findings = await run_exploration(
        prompt,
        exploration_id=exploration_id,
        project_id=ctx.project_id,
        kb_id=ctx.kb_id,
        cfg=cfg,
    )
    captured = findings[:max_f]
    finding_ids = await _persist_findings(ctx, captured, exploration_id)
    schedule_rebuild(ctx)
    return {
        "finding_count": len(finding_ids),
        "finding_ids": finding_ids,
        "project": project,
        "kb": kb,
    }


@mcp.tool()
async def brain2_activity(query: str | None = None, repo: str | None = None) -> dict:
    """Query your cross-repo ACTIVITY graph — what you've been working on.

    The activity graph accumulates automatically from every `brain2_capture`:
    repos, branches, files, work sessions, and the tasks behind them, across all
    your projects. Ask it things like "what was I doing in brain2 last" or "what
    touches the store layer".

    `query` seeds a semantic subgraph (omit for the whole graph); `repo` narrows
    to one repository. Returns `{nodes, edges, summary}` — `summary` is a short
    natural-language rollup; `nodes`/`edges` are the graph slice.
    """
    return await query_activity(query, repo=repo)


def main() -> None:
    get_settings()
    mcp.run()


if __name__ == "__main__":
    main()
