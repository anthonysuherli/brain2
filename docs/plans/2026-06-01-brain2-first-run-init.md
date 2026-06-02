# brain2 First-Run Init + KG Schema Wizard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a user opens a repo brain2 has never seen, a SessionStart hook detects the first run, Claude dispatches a background subagent that seeds a repo-scoped KB (local crawl + bounded web), then offers Delapan's full 5-stage KG schema wizard.

**Architecture:** Three layers, built bottom-up. (1) **Backend port** — bring Delapan's KG schema/builder Python layer into brain2, adapted to brain2's `Store` abstraction. (2) **MCP surface** — expose `propose_kg_schema`, `set_kg_schema`, `get_kg_schema`, `build_graph`, `graph`, `kg_stats`, and a cheap `kb_exists`. (3) **Plugin surface** — a SessionStart hook, two shared skill docs (`project-init.md`, `kg-schema-wizard.md`), and the `plugin.json` wiring + an `init_offered_at` offer-once stamp.

**Tech Stack:** Python 3.11, FastMCP (`mcp.server.fastmcp`), Supabase (Postgres+pgvector) via brain2's `Store` abstraction (local/sqlite/supabase backends), pytest (asyncio_mode=auto), ruff, pyright. Plugin layer: Claude Code hooks + markdown skills.

**Design doc:** `docs/plans/2026-06-01-brain2-first-run-init-design.md` (on `dev`).

**Source of truth for the port:** `/Users/suherli/Repositories/delapan/backend/delapan/knowledge_graph/{schema,builder,extractor,service,models}.py` and `delapan/interfaces/mcp/server.py:378-520`. **Read those before each port task.** brain2 = `/Users/suherli/Repositories/brain2/backend`. Work in the worktree at `.worktrees/feat/first-run-init`.

---

## Pre-flight (do once, before Task 1)

**Step 1: Set up the worktree's Python env**

The worktree shares git history but needs its own venv (PEP 660 editable installs pin to the original checkout). Run:

```bash
cd /Users/suherli/Repositories/brain2/.worktrees/feat/first-run-init/backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp /Users/suherli/Repositories/brain2/backend/.env .env 2>/dev/null || echo "no .env to copy — check secrets"
```

**Step 2: Verify clean baseline**

Run: `pytest -q`
Expected: existing suite passes (note the count; do not assume zero failures — record the baseline).

Run: `ruff check . && pyright`
Expected: record any pre-existing warnings as the baseline (the repo's pyright/ruff baselines are not zero — only *new* findings count against this work).

**Step 3: Confirm the DB has the schema tables**

The `kg_schemas` table (migration 0005) and `grounded_in` columns (0006) must exist in the target Supabase. Verify:

```bash
# Against the configured Supabase, confirm kg_schemas exists.
# If using the supabase MCP or psql, check: select to_regclass('public.kg_schemas');
```
Expected: `kg_schemas` resolves (non-null). If null, the migrations aren't applied — apply `supabase/migrations/0005_kg_schema.sql` and `0006_kg_grounded_in.sql` first.

---

## Phase 1 — Backend port (KG schema + builder)

The foundation. Everything else is blocked on this. Port from Delapan, adapt to brain2's `Store`. **Keep `exploration/`-style purity where Delapan has it** — `schema.py` and `extractor.py` are pure (no Supabase); `service.py` and `builder.py` own persistence.

### Task 1: Port KG schema models + proposer (`schema.py`)

**Files:**
- Read: `delapan/knowledge_graph/schema.py` (the Delapan original, 220 lines)
- Read: `delapan/knowledge_graph/models.py` (for `KGSchema`, `NodeType`, `RelationType` shapes)
- Create: `backend/brain2/knowledge_graph/schema.py`
- Modify: `backend/brain2/knowledge_graph/models.py` (add `KGSchema` + supporting models if not already present)
- Test: `backend/tests/knowledge_graph/test_schema.py`

`schema.py` provides: `propose_schema(findings, cfg, emergent=...)` (LLM draft ontology — pure, takes findings as dicts), `validate_schema(parsed) -> list[str]` (pure validation: attribute types ∈ {text,number,date,url,list,bool}, no dangling `relation_validity` pairs), and the `KGSchema` Pydantic model (`node_types` w/ `attributes`+`layer`, `relation_types`, `relation_validity`, `competency_questions`, `regime`).

**Step 1: Write the failing test for `validate_schema`**

```python
# backend/tests/knowledge_graph/test_schema.py
from brain2.knowledge_graph.schema import KGSchema, validate_schema


def test_validate_schema_flags_dangling_relation_validity():
    schema = KGSchema.model_validate({
        "node_types": [{"name": "service", "description": "a service", "examples": [],
                        "attributes": [], "layer": ""}],
        "relation_types": [{"name": "calls", "description": "x calls y"}],
        "relation_validity": [{"source_type": "service", "target_type": "ghost"}],
        "competency_questions": ["what calls what?"],
        "regime": "soft",
    })
    errors = validate_schema(schema)
    assert any("ghost" in e for e in errors)


def test_validate_schema_accepts_clean_schema():
    schema = KGSchema.model_validate({
        "node_types": [{"name": "service", "description": "a service", "examples": [],
                        "attributes": [{"name": "lang", "type": "text", "required": False,
                                        "description": "language"}], "layer": ""}],
        "relation_types": [{"name": "calls", "description": "x calls y"}],
        "relation_validity": [{"source_type": "service", "target_type": "service"}],
        "competency_questions": ["what calls what?"],
        "regime": "soft",
    })
    assert validate_schema(schema) == []
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/knowledge_graph/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: brain2.knowledge_graph.schema`.

**Step 3: Port the implementation**

Copy `delapan/knowledge_graph/schema.py` → `brain2/knowledge_graph/schema.py`. Change imports: `delapan.*` → `brain2.*`. Confirm `propose_schema` reads the LLM client the same way brain2's `exploration/` does (check `brain2/clients/` for the gateway client — match brain2's slug convention, not Delapan's). Add `KGSchema` + sub-models to `brain2/knowledge_graph/models.py` if not re-exported.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/knowledge_graph/test_schema.py -v`
Expected: PASS (both tests).

**Step 5: Lint + commit**

```bash
cd backend && ruff check brain2/knowledge_graph/schema.py brain2/knowledge_graph/models.py && ruff format brain2/knowledge_graph/schema.py
git add backend/brain2/knowledge_graph/schema.py backend/brain2/knowledge_graph/models.py backend/tests/knowledge_graph/test_schema.py
git commit -m "feat(kg): port KG intent schema models + validator from delapan"
```

---

### Task 2: Add KG-schema persistence to the Store (`service.py` → Store methods)

**Files:**
- Read: `delapan/knowledge_graph/service.py:130-180` (the `kg_schema`, `set_kg_intent`, `kg_schema_view` functions — they call `sb.table("kg_schemas")` directly)
- Modify: `backend/brain2/store/base.py` (add abstract methods)
- Modify: `backend/brain2/store/supabase.py` (implement against `kg_schemas`)
- Modify: `backend/brain2/store/sqlite.py` (local-tier parity — a `kg_schemas` table)
- Test: `backend/tests/store/test_kg_schema_store.py`

Delapan's `service.py` hits `sb.table(...)` directly. brain2 routes through `Store`, so the persistence becomes **store methods**: `get_kg_intent(kb_id) -> dict | None` (max version), `set_kg_intent(org_id, kb_id, schema) -> dict` (insert version+1), and reuse existing `kg_stats`/`list_kg_nodes` for the `emergent` half of `kg_schema_view`.

**Step 1: Write the failing test (sqlite backend — no network)**

```python
# backend/tests/store/test_kg_schema_store.py
import pytest
from brain2.store.sqlite import SqliteStore  # adjust to actual class name


@pytest.fixture
def store(tmp_path):
    return SqliteStore(str(tmp_path / "t.db"))


def test_set_then_get_kg_intent_versions(store):
    org, kb = "org1", "kb1"
    s1 = store.set_kg_intent(org, kb, {"node_types": [], "competency_questions": ["q1"]})
    assert s1["version"] == 1
    s2 = store.set_kg_intent(org, kb, {"node_types": [], "competency_questions": ["q2"]})
    assert s2["version"] == 2
    latest = store.get_kg_intent(kb)
    assert latest["schema"]["competency_questions"] == ["q2"]


def test_get_kg_intent_none_when_unset(store):
    assert store.get_kg_intent("nope") is None
```

**Step 2: Run to verify it fails**

Run: `pytest backend/tests/store/test_kg_schema_store.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'set_kg_intent'`.

**Step 3: Implement**

- `base.py`: declare `get_kg_intent` / `set_kg_intent` abstract.
- `supabase.py`: port from Delapan `service.py` — `set` inserts `{org_id, kb_id, version: max+1, schema}`; `get` selects max version. Writes via service client (per the 0005 migration comment).
- `sqlite.py`: add a `kg_schemas(kb_id, version, schema_json, created_at)` table in `_ensure_schema`; implement both methods.

**Step 4: Run to verify it passes**

Run: `pytest backend/tests/store/test_kg_schema_store.py -v`
Expected: PASS.

**Step 5: Lint + commit**

```bash
git add backend/brain2/store/base.py backend/brain2/store/supabase.py backend/brain2/store/sqlite.py backend/tests/store/test_kg_schema_store.py
git commit -m "feat(store): kg_schemas persistence (get/set intent, versioned) across backends"
```

---

### Task 3: Port the extractor + builder (`extractor.py`, `builder.py`)

**Files:**
- Read: `delapan/knowledge_graph/extractor.py` (219), `delapan/knowledge_graph/builder.py` (313)
- Create: `backend/brain2/knowledge_graph/extractor.py`
- Create: `backend/brain2/knowledge_graph/builder.py`
- Test: `backend/tests/knowledge_graph/test_builder.py`

`extractor.py` is pure (LLM extraction of nodes/edges from findings; schema-steered when intent given). `builder.py` orchestrates: load findings → extract → dedupe via `match_kg_nodes` → persist via `upsert_kg_nodes/edges` (brain2's store already has these). Adapt `build_graph(ctx, ...)` to take brain2's `TenantContext` and route persistence through `get_store(...)` instead of `service_client()` directly.

**Step 1: Write a failing test with a stubbed extractor**

```python
# backend/tests/knowledge_graph/test_builder.py
import pytest
from brain2.knowledge_graph import builder


@pytest.mark.asyncio
async def test_build_graph_persists_extracted_nodes(monkeypatch, fake_ctx, fake_store):
    async def fake_extract(findings, schema, cfg):
        return {"nodes": [{"label": "FastMCP", "type": "library"}],
                "edges": []}
    monkeypatch.setattr(builder, "extract_graph", fake_extract)
    monkeypatch.setattr(builder, "get_store", lambda *a, **k: fake_store)
    result = await builder.build_graph(fake_ctx, rebuild=True, use_schema=False)
    assert result["nodes_created"] >= 1
    assert fake_store.upserted_nodes  # fake records calls
```

(Define `fake_ctx`/`fake_store` fixtures in `conftest.py` — `fake_store` records `upsert_kg_nodes` calls and returns ids.)

**Step 2: Run to verify it fails**

Run: `pytest backend/tests/knowledge_graph/test_builder.py -v`
Expected: FAIL — module/function missing.

**Step 3: Port the implementation**

Copy both files, rewrite imports `delapan.*` → `brain2.*`, and replace direct `service_client()` persistence with `get_store(ctx.access_token, org_id=ctx.org_id)` calls (`upsert_kg_nodes`, `upsert_kg_edges`, `match_kg_nodes`, finding reads). Drop Delapan's `refresh_project_description` for v1 (YAGNI — note it as a follow-up). Keep `grounded_in` provenance (the 0006 columns exist).

**Step 4: Run to verify it passes**

Run: `pytest backend/tests/knowledge_graph/test_builder.py -v`
Expected: PASS.

**Step 5: Lint + commit**

```bash
git add backend/brain2/knowledge_graph/extractor.py backend/brain2/knowledge_graph/builder.py backend/tests/knowledge_graph/
git commit -m "feat(kg): port extractor + builder (schema-steered, store-routed)"
```

---

## Phase 2 — MCP surface

### Task 4: Add the `kb_exists` MCP tool (the hook's guard)

**Files:**
- Modify: `backend/brain2/interfaces/mcp/server.py`
- Test: `backend/tests/interfaces/test_mcp_kb_exists.py`

A cheap check the SessionStart hook calls to decide first-run. Must **not** create the KB (`create=False`), and must distinguish "no KB" from "backend error" (the hook fails closed on error → no init).

**Step 1: Failing test**

```python
# backend/tests/interfaces/test_mcp_kb_exists.py
import pytest
from brain2.interfaces.mcp import server


@pytest.mark.asyncio
async def test_kb_exists_false_for_unknown(monkeypatch, ...):
    # resolve_tenant(create=False) raises "not found" → tool returns {exists: False}
    out = await server.brain2_kb_exists("ghost-proj", "ghost-kb")
    assert out == {"exists": False, "project": "ghost-proj", "kb": "ghost-kb"}
```

**Step 2: Run → FAIL** (`brain2_kb_exists` undefined).

**Step 3: Implement**

```python
@mcp.tool()
async def brain2_kb_exists(project: str, kb: str) -> dict:
    """Cheap first-run guard: does a brain2 KB exist for this project/kb?
    Never creates anything. Returns {exists: bool, project, kb}. On a genuine
    backend error, RAISES (the caller must fail closed and skip init)."""
    try:
        resolve_tenant(project, kb, create=False)
        return {"exists": True, "project": project, "kb": kb}
    except RuntimeError as exc:
        if "not found" in str(exc).lower():
            return {"exists": False, "project": project, "kb": kb}
        raise
```

**Step 4: Run → PASS.**

**Step 5: Commit**

```bash
git add backend/brain2/interfaces/mcp/server.py backend/tests/interfaces/test_mcp_kb_exists.py
git commit -m "feat(mcp): brain2_kb_exists guard for first-run detection"
```

---

### Task 5: Surface the KG-schema + build MCP tools

**Files:**
- Read: `delapan/interfaces/mcp/server.py:378-520` (the tool bodies)
- Modify: `backend/brain2/interfaces/mcp/server.py`
- Test: `backend/tests/interfaces/test_mcp_kg_tools.py`

Add five tools mirroring Delapan, renamed `brain2_*`, routed through brain2's store/builder: `brain2_propose_kg_schema`, `brain2_set_kg_schema`, `brain2_get_kg_schema`, `brain2_build_graph`, `brain2_graph`, `brain2_kg_stats`. Reuse `KGSchema.model_validate` + `validate_schema` in `set` (Task 1), `set_kg_intent`/`get_kg_intent` (Task 2), `build_graph` (Task 3).

**Step 1: Failing test** — `brain2_set_kg_schema` rejects a malformed schema with `{ok: False, errors: [...]}` and accepts a clean one (mock the store's `set_kg_intent`).

**Step 2: Run → FAIL.**

**Step 3: Implement** the six tools, copying Delapan's docstrings (adjust tool names + brain2 substrate language: "findings" stay findings). `propose` reads findings via the store; `build_graph` calls `builder.build_graph(ctx, ...)`.

**Step 4: Run → PASS.**

**Step 5: Commit**

```bash
git add backend/brain2/interfaces/mcp/server.py backend/tests/interfaces/test_mcp_kg_tools.py
git commit -m "feat(mcp): surface propose/set/get_kg_schema + build_graph/graph/kg_stats"
```

---

### Task 6: Smoke-test the MCP server boots with the new tools

**Step 1:** Run the server briefly and assert it registers without import errors.

Run: `python -c "from brain2.interfaces.mcp import server; print(sorted(t for t in dir(server) if t.startswith('brain2_')))"`
Expected: lists `brain2_build_graph`, `brain2_capture`, `brain2_explore`, `brain2_get_kg_schema`, `brain2_graph`, `brain2_kb_exists`, `brain2_kg_stats`, `brain2_propose_kg_schema`, `brain2_resume`, `brain2_set_kg_schema`, `brain2_activity`.

**Step 2:** Full suite + lint gate.

Run: `pytest -q && ruff check . && pyright`
Expected: no *new* failures vs the Pre-flight baseline.

**Step 3: Commit** (if any fixups needed).

---

## Phase 3 — Plugin surface (skills + hook)

### Task 7: Port the KG schema wizard as a shared skill doc

**Files:**
- Read: `/Users/suherli/Repositories/delapan/skills/graph/schema.md` (the 5-stage wizard — the canonical source)
- Create: `skills/_shared/kg-schema-wizard.md`

Near-verbatim port. Substrate adaptations: (1) MCP tool names `mcp__delapan__delapan_*` → `mcp__brain2__brain2_*`; (2) "the KB's findings" stays (brain2 findings); (3) Stage 0 mode-select calls `brain2_get_kg_schema`; (4) Stage 5 build calls `brain2_build_graph(use_schema=True, rebuild=True)`; (5) drop references to delapan-only skills (`/delapan:build explore` → `/brain2:explore`; `/delapan:maintain` → omit or map to nearest brain2 verb). Keep all five stages, the one-question-at-a-time `AskUserQuestion` discipline, and the Reconfigure flow.

**Verify:** Read the finished doc end-to-end; confirm every tool name resolves to a real `brain2_*` tool from Task 5, and no `delapan:` skill references remain.

```bash
grep -n "delapan" skills/_shared/kg-schema-wizard.md   # expect: no matches
git add skills/_shared/kg-schema-wizard.md
git commit -m "docs(skill): port 5-stage KG schema wizard to brain2 substrate"
```

---

### Task 8: Write the project-init shared skill doc

**Files:**
- Create: `skills/_shared/project-init.md`
- Read for tone/shape: existing `skills/explore/SKILL.md`, `skills/_shared/*` conventions

The brief the init subagent follows. Contents:

- **Role:** dispatched as a background subagent on first run; not interactive.
- **Phase A (local, no network):** crawl repo structure (tree, languages, entry points, manifests, build/test config), git (recent log, branches, contributors, churn hotspots), metadata (README, CLAUDE.md/AGENTS.md, docs/, license). Persist each as a finding via `mcp__brain2__brain2_capture` / the ingest path. Creating the KB is the concurrency lock.
- **Phase B (bounded web):** pick 2–4 high-value external facts from Phase A; one bounded `mcp__brain2__brain2_explore` pass with a small fixed budget; on failure, skip (local findings stand).
- **Output contract:** return a compact structured result `{kb, local_count, web_count, draft_ready: true}`. As a background subagent, the final message *is* the return value (raw data, not prose).
- **Hard stops:** never block; never run an open-ended crawl; web budget is fixed.

**Verify:** Read end-to-end; confirm tool names resolve and the two phases + output contract are unambiguous.

```bash
git add skills/_shared/project-init.md
git commit -m "docs(skill): project-init subagent brief (local crawl + bounded web)"
```

---

### Task 9: Write the SessionStart hook guard

**Files:**
- Create: `hooks/first-run-init.py`
- Test: `backend/tests/hooks/test_first_run_guard.py` (or a `hooks/` test if a Python-importable module)

A SessionStart hook. Reads hook input (cwd) from stdin/env, resolves repo identity, calls `brain2_kb_exists`, and on first-run emits `additionalContext` injecting the directive. Make the logic importable (pure function `decide(cwd) -> str | None`) so it's testable without the hook harness.

**Step 1: Failing test**

```python
# backend/tests/hooks/test_first_run_guard.py
from hooks.first_run_init import repo_identity, build_directive  # adjust path


def test_repo_identity_prefers_remote(tmp_git_repo_with_remote):
    ident = repo_identity(tmp_git_repo_with_remote)
    assert ident.startswith("github.com") or "://" not in ident  # normalized


def test_build_directive_mentions_background_dispatch():
    d = build_directive(project="myrepo", kb="main")
    assert "background" in d.lower()
    assert "project-init" in d.lower() or "init subagent" in d.lower()
```

**Step 2: Run → FAIL.**

**Step 3: Implement**

- `repo_identity(cwd)`: `git remote get-url origin` normalized (strip scheme/`.git`, lowercase); fallback to repo root via `git rev-parse --show-toplevel`; if not a git repo → return `None`.
- `decide(cwd)`: identity `None` → return `None` (silent). Else derive `(project, kb)`, call the backend `kb_exists`. `exists True` → `None`. `exists False` → `build_directive(...)`. **Any exception → `None`** (fail closed). 
- `build_directive(project, kb)`: a string telling Claude to announce one line, then dispatch the init subagent (`Agent`, `run_in_background`) following `skills/_shared/project-init.md`, and to offer the schema wizard at the next turn boundary on completion (offer once).
- `main()`: read SessionStart hook JSON from stdin, call `decide`, and if non-None print the `additionalContext` JSON envelope the hook API expects; else exit 0 silently.

**Step 4: Run → PASS.**

**Step 5: Commit**

```bash
git add hooks/first-run-init.py backend/tests/hooks/
git commit -m "feat(hook): SessionStart first-run guard (repo identity + kb_exists → directive)"
```

---

### Task 10: Wire the hook + offer-once stamp

**Files:**
- Modify: `.claude-plugin/plugin.json` (add `hooks`)
- Modify: `backend/brain2/interfaces/mcp/server.py` (stamp `init_offered_at`)
- Possibly: a migration if `init_offered_at` needs a column (check `kbs` table first)

**Step 1: Add the hook to `plugin.json`**

```json
"hooks": {
  "SessionStart": [
    { "hooks": [ { "type": "command",
        "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/first-run-init.py" } ] }
  ]
}
```

(Verify the exact hooks schema against `plugin-dev:hook-development` — match the array/`matcher` shape the installed Claude Code version expects.)

**Step 2: Offer-once stamp**

Check whether `kbs` has a spare metadata column. If not, add `init_offered_at timestamptz` via a new migration `0007_kb_init_offered.sql`. Expose a tiny `brain2_mark_init_offered(project, kb, at)` tool (or fold into `set_kg_schema`'s success path). The wizard offer reads it: if set, don't re-offer.

**Step 3: Verify wiring**

Restart Claude Code in the worktree (or reload the plugin) and confirm the hook is registered:
- Fresh repo (no KB) → one-line announce + background init dispatched.
- Second launch → silent.
- Non-git dir → silent.

**Step 4: Commit**

```bash
git add .claude-plugin/plugin.json backend/brain2/interfaces/mcp/server.py supabase/migrations/0007_kb_init_offered.sql
git commit -m "feat(plugin): wire SessionStart hook + offer-once init stamp"
```

---

## Phase 4 — End-to-end verification

### Task 11: Full first-run walkthrough

**REQUIRED SKILL:** Use superpowers:verification-before-completion.

**Step 1:** In a throwaway git repo with no brain2 KB, launch a session. Observe: one-line announce; background subagent dispatched.

**Step 2:** Wait for completion. Inspect the KB: `brain2_kg_stats` / list findings → Phase-A findings present; Phase-B findings present (or cleanly skipped).

**Step 3:** Accept the schema offer. Walk all 5 wizard stages; confirm each uses `AskUserQuestion` one-at-a-time, `set_kg_schema` versions the row, and `build_graph` produces nodes/edges.

**Step 4:** Re-launch the same repo → silent (KB exists). Decline path: in a second throwaway repo, decline the offer → findings persist, graph empty, no re-offer on next launch.

**Step 5:** Gate: `pytest -q && ruff check . && pyright` — no new failures vs baseline.

**Step 6: Final commit + update design doc**

Mark the design doc's open-dependency note resolved (the backend was *ported*, not merely surfaced). Commit.

```bash
git add docs/plans/2026-06-01-brain2-first-run-init-design.md
git commit -m "docs: mark KG backend port complete; first-run init verified end-to-end"
```

---

## Notes for the implementer

- **Slug convention:** brain2's chat/agent path and pipeline path may use different model-slug formats (dots vs hyphens) like Delapan does. When porting `propose_schema`/`extractor` LLM calls, match **brain2's** existing `exploration/` client usage — do not copy Delapan's slugs.
- **Store routing is the #1 porting hazard.** Delapan calls `service_client()` inline; brain2 *must* go through `get_store(...)`. Every `sb.table(...)` in the Delapan source becomes a store method call. Tasks 2 and 3 are where this bites.
- **Local tier parity:** brain2 has a local/sqlite backend Delapan lacks. KG-schema persistence (Task 2) needs the sqlite path or the wizard breaks for local users. Builder persistence (Task 3) already has `upsert_kg_nodes/edges` in both backends — verify the sqlite versions exist and work.
- **YAGNI cuts:** skip `refresh_project_description`, incremental build, and `communities` for v1. Note them as follow-ups, don't build them.
- **DRY:** the wizard doc (Task 7) is the *only* copy of the 5-stage flow — `project-init.md` points to it, doesn't restate it.
