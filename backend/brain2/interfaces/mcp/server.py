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

import os

from mcp.server.fastmcp import FastMCP

from brain2.agent.preamble import select_preamble
from brain2.capture.models import WorkspaceSnapshot
from brain2.capture.service import persist_snapshot
from brain2.config import get_config, get_settings
from brain2.exploration import run_exploration
from brain2.interfaces.mcp.banner import BRAIN2_BANNER
from brain2.interfaces.mcp.tenancy import resolve_store, resolve_tenant
from brain2.knowledge_graph.activity import query_activity, schedule_activity_update
from brain2.knowledge_graph.builder import build_graph
from brain2.knowledge_graph.drift import assess_drift
from brain2.knowledge_graph.models import KGSchema
from brain2.knowledge_graph.schema import propose_schema, validate_schema
from brain2.livingdocs.distill import run_distill, schedule_distill
from brain2.livingdocs.notes import persist_note
from brain2.livingdocs.paths import DocPaths
from brain2.livingdocs.policy import NotePolicy, load_policy, save_policy
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


async def _note_impl(
    project, kb, project_path, content, session_id, title, captured_at="", source="agent"
):
    ctx = resolve_tenant(project, kb, create=True)
    res = await persist_note(
        ctx,
        project_path=project_path,
        kb=kb,
        content=content,
        session_id=session_id,
        title=title,
        captured_at=captured_at,
        source=source,
    )
    schedule_distill(ctx, project_path=project_path, kb=kb)
    return {**res, "project": project, "kb": kb}


@mcp.tool()
async def brain2_note(
    project: str,
    kb: str,
    project_path: str,
    content: str,
    session_id: str,
    title: str,
    captured_at: str = "",
    source: str = "agent",
) -> dict:
    """Persist a session note: a `note` Finding (searchable, feeds resume) AND a
    markdown file under .brain2/notes/<kb>/. Then schedules a debounced re-distill of
    the curated doc tree. Called by the Stop hook at session end. `content` should be
    rendered per the KB's note policy (brain2_notes_policy_get). Returns
    {finding_id, note_path, project, kb}."""
    return await _note_impl(
        project, kb, project_path, content, session_id, title, captured_at, source
    )


def _policy_get_impl(project, kb, project_path):
    paths = DocPaths(project_path=project_path, kb=kb)
    pol = load_policy(paths)
    return {"policy": pol.model_dump(), "project": project, "kb": kb}


def _policy_set_impl(project, kb, project_path, policy):
    try:
        pol = NotePolicy.model_validate(policy)
    except Exception as exc:  # noqa: BLE001 — return errors, never crash the tool
        return {"ok": False, "errors": [str(exc)], "project": project, "kb": kb}
    save_policy(DocPaths(project_path=project_path, kb=kb), pol)
    return {"ok": True, "policy": pol.model_dump(), "project": project, "kb": kb}


async def _distill_impl(project, kb, project_path, force=False):
    ctx = resolve_tenant(project, kb, create=True)
    if force:
        res = await run_distill(ctx, project_path=project_path, kb=kb)
        return {"distilled": True, "forced": True, **res, "project": project, "kb": kb}
    schedule_distill(ctx, project_path=project_path, kb=kb)
    return {"distilled": False, "forced": False, "scheduled": True, "project": project, "kb": kb}


@mcp.tool()
def brain2_notes_policy_get(project: str, kb: str, project_path: str) -> dict:
    """Read the per-KB note-taking policy (section template + free-text steer) from
    .brain2/notes-policy.json. Returns {policy: {sections, steer}, project, kb}.
    Returns the default policy if none is set yet."""
    return _policy_get_impl(project, kb, project_path)


@mcp.tool()
def brain2_notes_policy_set(project: str, kb: str, project_path: str, policy: dict) -> dict:
    """Persist the per-KB note-taking policy. `policy` = {sections: [{name, enabled}],
    steer: str}. Validates before writing; on a bad shape returns {ok: False, errors}.
    On success returns {ok: True, policy, project, kb}. Used by /brain2:notes."""
    return _policy_set_impl(project, kb, project_path, policy)


@mcp.tool()
async def brain2_distill(project: str, kb: str, project_path: str, force: bool = False) -> dict:
    """(Re)build the curated .brain2/docs/ tree from the KB's session notes. `force=True`
    distills now and returns {distilled, doc_count, folders}; otherwise it just nudges the
    debounced background distiller. Used by /brain2:docs --rebuild."""
    return await _distill_impl(project, kb, project_path, force)


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
async def brain2_projects() -> dict:
    """List every repo+branch you've captured to, most-recent first.

    Powers the `/brain2:pickup` selector: each project carries its branches with
    `last_activity` + `snapshot_count` chips so you can jump back into any repo you've
    been working in — not just the current git checkout. Org-scoped on cloud, the
    single local store on the free tier. Returns
    `{projects: [{project, project_id, kbs: [{kb, kb_id, last_activity, snapshot_count}]}]}`.
    """
    store = resolve_store()
    return {"projects": store.list_projects()}


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

    Never creates anything. Returns {exists: bool, init_offered: bool, project, kb}.
    ``init_offered`` is True when the KG schema wizard has already been offered
    (migration 0007 stamp) — callers use this to skip the re-offer.
    On genuine backend errors (non-"not found" RuntimeErrors), RAISES so the
    caller fails closed — don't silently return exists=False on a backend outage.
    """
    try:
        ctx = resolve_tenant(project, kb, create=False)
        store = get_store(ctx.access_token, org_id=ctx.org_id)
        init_offered = store.get_init_offered(ctx.kb_id)
        return {
            "exists": True,
            "init_offered": init_offered,
            "project": project,
            "kb": kb,
        }
    except RuntimeError as exc:
        if "not found" in str(exc).lower():
            return {"exists": False, "init_offered": False, "project": project, "kb": kb}
        raise


@mcp.tool()
async def brain2_mark_init_offered(project: str, kb: str) -> dict:
    """Stamp the KB with the time the KG schema wizard was offered.

    Called exactly once after the first-run schema offer is surfaced — prevents
    re-offering on subsequent SessionStart events. Safe to call even if migration
    0007 has not been applied (best-effort, never raises).
    Returns {marked: bool, project, kb}.
    """
    try:
        ctx = resolve_tenant(project, kb, create=False)
        store = get_store(ctx.access_token, org_id=ctx.org_id)
        store.mark_init_offered(ctx.kb_id)
        return {"marked": True, "project": project, "kb": kb}
    except Exception:  # noqa: BLE001 — best-effort stamp; never fail the session
        return {"marked": False, "project": project, "kb": kb}


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
async def brain2_schema_drift(project: str, kb: str) -> dict:
    """Should brain2 offer to (re)design this KB's KG schema right now?

    The trigger behind the self-maintaining loop. Reads the built graph's type
    distribution against the KB's approved intent schema (no extra LLM call) and
    returns a verdict:
      - ``mode``: ``"cold_start"`` (no schema yet, enough collected to propose one),
        ``"drift"`` (a schema is set but residual / off-ontology nodes crossed the
        threshold), ``"ok"`` (the graph fits), or ``"empty"`` (too small to judge).
      - ``should_offer``: whether to surface the offer NOW — debounced so a declined
        offer doesn't re-nag every session.
      - ``offer_line``: the ready-to-show, one-line turn-boundary offer (null unless
        ``should_offer``).
      - ``residual`` / ``ratio`` / ``residual_types``: the off-ontology cluster — the
        seed the ``/brain2:schema`` wizard reshapes around.

    Gated by ``BRAIN2_SCHEMA_DRIFT`` (default on); returns ``mode="off"`` when
    disabled. Best-effort — never raises; an unbuilt graph reads as ``"empty"``."""
    if os.getenv("BRAIN2_SCHEMA_DRIFT", "1") == "0":
        return {"mode": "off", "should_offer": False, "offer_line": None, "project": project, "kb": kb}
    try:
        ctx = resolve_tenant(project, kb, create=False)
    except Exception:  # noqa: BLE001 — unknown KB: nothing to judge, stay quiet
        return {"mode": "empty", "should_offer": False, "offer_line": None, "project": project, "kb": kb}
    store = get_store(ctx.access_token, org_id=ctx.org_id)
    cfg = get_config().drift
    verdict = assess_drift(
        store,
        ctx.kb_id,
        cfg,
        init_offered=store.get_init_offered(ctx.kb_id),
        drift_marker=store.get_drift_marker(ctx.kb_id),
    )
    return {**verdict.to_dict(), "project": project, "kb": kb}


@mcp.tool()
async def brain2_mark_drift_offered(project: str, kb: str, residual: int) -> dict:
    """Stamp that a schema-drift offer was surfaced for the KB, at ``residual`` count.

    Call once right after surfacing the drift ``offer_line`` (whether or not the
    user accepts). Debounces re-offers: the next drift offer only re-surfaces once
    residual grows by the configured ``rearm_delta`` beyond this stamp — so a steady
    "no" stays quiet. Best-effort; never raises. Returns
    ``{marked, project, kb, residual}``."""
    try:
        ctx = resolve_tenant(project, kb, create=False)
        store = get_store(ctx.access_token, org_id=ctx.org_id)
        store.set_drift_marker(ctx.kb_id, int(residual))
        return {"marked": True, "project": project, "kb": kb, "residual": int(residual)}
    except Exception:  # noqa: BLE001 — best-effort stamp; never fail the session
        return {"marked": False, "project": project, "kb": kb, "residual": residual}


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

    d = min(depth or cfg.graph_default_depth, cfg.graph_max_depth)
    g = store.get_kg_subgraph(
        ctx.kb_id,
        seed_node_ids=seed_ids,
        node_cap=cfg.graph_node_cap,
        edge_cap=cfg.graph_edge_cap,
        depth=d,
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
