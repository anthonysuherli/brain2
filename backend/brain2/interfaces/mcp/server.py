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
from brain2.knowledge_graph.builder import build_graph
from brain2.knowledge_graph.models import KGSchema
from brain2.knowledge_graph.schema import propose_schema, validate_schema
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
async def brain2_kb_exists(project: str, kb: str) -> dict:
    """Cheap first-run guard: does a brain2 KB exist for this project/kb?

    Never creates anything. Returns {exists: bool, project, kb}.
    On genuine backend errors (non-"not found" RuntimeErrors), RAISES so the
    caller fails closed — don't silently return exists=False on a backend outage.
    """
    try:
        resolve_tenant(project, kb, create=False)
        return {"exists": True, "project": project, "kb": kb}
    except RuntimeError as exc:
        if "not found" in str(exc).lower():
            return {"exists": False, "project": project, "kb": kb}
        raise


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


@mcp.tool()
async def brain2_propose_kg_schema(
    project: str, kb: str, max_findings: int | None = None
) -> dict:
    """STEP 1 of KG-intent co-design. Mine the KB's findings and propose a draft
    target ontology: ``node_types``, ``relation_types``, ``relation_validity``, and
    ``competency_questions``. Persists nothing — review with the user, then approve
    with ``brain2_set_kg_schema``. If the KB has no findings the draft is a
    generic default plus a ``note``."""
    ctx = resolve_tenant(project, kb, create=False)
    cfg = get_config().knowledge_graph
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    n = max_findings or cfg.max_findings
    result = store.list_findings(ctx.kb_id, limit=n)
    findings = [f for f in (result.get("findings") or []) if isinstance(f, dict)]
    stats = store.kg_stats(ctx.kb_id)
    # Build an emergent hint from the current graph's type distribution.
    emergent: dict | None = None
    if stats.get("node_count", 0) or stats.get("edge_count", 0):
        emergent = {
            "node_types": list((stats.get("by_type") or {}).keys()),
            "relations": list((stats.get("by_relation") or {}).keys()),
        }
    draft = await propose_schema(findings, cfg, emergent=emergent)
    out = draft.model_dump()
    if not findings:
        out["note"] = "KB has no findings — explore or ingest first for a grounded proposal."
    return out


@mcp.tool()
async def brain2_set_kg_schema(project: str, kb: str, schema: dict) -> dict:
    """STEP 2 of KG-intent co-design. Validate and persist the user-approved KG
    schema dict (as returned by ``brain2_propose_kg_schema``, edited as the user
    wishes) as a new version. Returns ``{ok: true, schema}`` on success, or
    ``{ok: false, errors}`` if the schema is malformed (nothing is saved).
    The next ``brain2_build_graph(use_schema=True)`` builds against it."""
    ctx = resolve_tenant(project, kb, create=False)
    try:
        parsed = KGSchema.model_validate(schema)
    except Exception as exc:  # noqa: BLE001 — surface validation errors to the caller
        return {"ok": False, "errors": [f"schema does not parse: {exc}"]}
    errors = validate_schema(parsed)
    if errors:
        return {"ok": False, "errors": errors}
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    stored = store.set_kg_intent(ctx.org_id, ctx.kb_id, parsed.model_dump())
    return {"ok": True, "schema": stored}


@mcp.tool()
async def brain2_get_kg_schema(project: str, kb: str) -> dict:
    """Both ontologies for the KB: ``intent`` (the user-approved target schema set
    via ``brain2_set_kg_schema``, or null) and ``emergent`` (the node/relation types
    actually present in the built graph, with totals). Compare to see drift."""
    ctx = resolve_tenant(project, kb, create=False)
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    intent = store.get_kg_intent(ctx.kb_id)
    emergent = store.kg_stats(ctx.kb_id)
    return {"intent": intent, "emergent": emergent}


@mcp.tool()
async def brain2_build_graph(
    project: str,
    kb: str,
    max_findings: int | None = None,
    rebuild: bool = True,
    use_schema: bool = True,
) -> dict:
    """Build/refresh the KB's knowledge graph from its findings. An LLM extracts
    entities + relationships, which are deduped and written to kg_nodes/kg_edges.
    ``rebuild=True`` (default) clears the existing graph first (clean rebuild).
    ``use_schema=True`` steers extraction with the KB's approved intent schema if
    one was set via ``brain2_set_kg_schema``; with none set it builds free-form.
    Returns ``{findings_scanned, nodes_created, edges_created, node_count, edge_count}``."""
    ctx = resolve_tenant(project, kb, create=False)
    return await build_graph(
        ctx,
        max_findings=max_findings,
        rebuild=rebuild,
        use_schema=use_schema,
    )


@mcp.tool()
async def brain2_graph(
    project: str, kb: str, focus: str | None = None, depth: int | None = None
) -> dict:
    """Read the KB's knowledge graph: the full graph (capped) or a depth-bounded
    subgraph around nodes whose label matches ``focus``. Returns nodes/edges +
    counts. Empty until ``brain2_build_graph`` has run."""
    ctx = resolve_tenant(project, kb, create=False)
    cfg = get_config().public_api
    store = get_store(ctx.access_token, org_id=ctx.org_id)

    seed_ids: list[str] | None = None
    if focus:
        # Semantic seed: find nodes whose label is closest to `focus`.
        from brain2.clients.embeddings import embed_text

        try:
            emb = await embed_text(focus)
            matches = await store.match_kg_nodes(
                ctx.kb_id,
                query_embedding=emb,
                match_count=5,
                min_similarity=0.0,
            )
            seed_ids = [m["id"] for m in matches if m.get("id")]
        except Exception:  # noqa: BLE001 — degrade gracefully to whole-graph
            seed_ids = None

    g = store.get_kg_subgraph(
        ctx.kb_id,
        seed_node_ids=seed_ids,
        node_cap=cfg.graph_node_cap,
        edge_cap=cfg.graph_edge_cap,
    )
    return {**g, "node_count": len(g.get("nodes", [])), "edge_count": len(g.get("edges", []))}


@mcp.tool()
async def brain2_kg_stats(project: str, kb: str) -> dict:
    """KG metrics: node/edge totals plus counts by node type and by relation."""
    ctx = resolve_tenant(project, kb, create=False)
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    return store.kg_stats(ctx.kb_id)


def main() -> None:
    get_settings()
    mcp.run()


if __name__ == "__main__":
    main()
