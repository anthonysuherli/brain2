# Personal Knowledge Engine — Phase A Implementation Plan (Concept Tier + Write Path)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `concept` node tier to the existing activity KG plus the distillation write path that creates and reinforces concepts from a KB's findings — driven manually (no triggers yet).

**Architecture:** Concepts are `kg_nodes` rows with `type='concept'`, evidence via the existing `grounded_in` field, bound to activity via `about` edges. A new `knowledge_graph/distill.py` runs `select → synthesize (LLM) → evaluate (critic) → reconcile → upsert`. Reconcile in Phase A is limited to **new vs reinforce** (refine/contradict deferred to Phase C). One new Store primitive, `update_kg_node`, lets a re-distilled concept overwrite its payload (today's `upsert_kg_nodes` merges with existing-wins and cannot overwrite).

**Tech Stack:** Python 3.11, pytest (`asyncio_mode=auto`), SQLite + sqlite-vec, Pydantic, `structured_completion` (AI Gateway), `embed_batch`.

**Reference (design):** `docs/plans/2026-06-01-personal-knowledge-engine-design.md` (§3 model, §4 pipeline, §7 store changes).

**Scope guard (YAGNI):** No capture/explore triggers (Phase B), no `/v1/context` endpoint or preamble banding (Phase C), no `refines`/`contradicts` reconciliation (Phase C). Phase A ends when a manual `distill_kb(...)` call over a KB's findings produces `concept` nodes with evidence + `about` edges, idempotently.

---

## Task 1: `update_kg_node` on the Store protocol

**Files:**
- Modify: `br8n/store/base.py` (KG section, after `upsert_kg_edges` ~line 118)

**Step 1: Add the protocol method**

In `br8n/store/base.py`, inside `class Store(Protocol)`, after `upsert_kg_edges`:

```python
    async def update_kg_node(
        self,
        kb_id: str,
        node_id: str,
        *,
        properties: dict,
        grounded_in: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> None:
        """Overwrite a node's payload (unlike upsert_kg_nodes, which merges with
        existing-wins). `properties` replaces wholesale; `grounded_in` replaces when
        given; `embedding` re-indexes the vector when given. Used to re-distill a
        concept's body/confidence/version in place."""
        ...
```

**Step 2: Commit**

```bash
git add br8n/store/base.py
git commit -m "feat(store): add update_kg_node to Store protocol"
```

---

## Task 2: `update_kg_node` on SQLiteStore

**Files:**
- Modify: `br8n/store/sqlite.py` (after `_merge_kg_node`, ~line 548)
- Test: `tests/test_kg_store_sqlite.py`

**Step 1: Write the failing test**

Append to `tests/test_kg_store_sqlite.py`:

```python
# --- update_kg_node (overwrite, not merge) ----------------------------------


async def test_update_kg_node_overwrites_properties(store):
    [nid] = await store.upsert_kg_nodes(
        "akb", [_node("concept", "x compounds", properties={"body": "old", "version": 1})]
    )
    await store.update_kg_node(
        "akb", nid, properties={"body": "new", "version": 2}
    )
    rows = store.list_kg_nodes("akb", type="concept")
    props = next(r for r in rows if r["id"] == nid)["properties"]
    assert props["body"] == "new"
    assert props["version"] == 2


async def test_update_kg_node_replaces_grounded_and_reembeds(store):
    [nid] = await store.upsert_kg_nodes(
        "akb",
        [_node("concept", "y", embedding=_vec([1.0, 0.0]), grounded_in=["f1"])],
    )
    await store.update_kg_node(
        "akb", nid, properties={"body": "b"},
        grounded_in=["f1", "f2"], embedding=_vec([0.0, 1.0]),
    )
    # grounded replaced
    rows = store.list_kg_nodes("akb", type="concept")
    assert next(r for r in rows if r["id"] == nid)["grounded_in"] == ["f1", "f2"]
    # re-embedded: a query near the NEW vector returns it
    hits = await store.match_kg_nodes("akb", _vec([0.0, 1.0]), match_count=1, min_similarity=0.5)
    assert hits and hits[0]["id"] == nid
```

**Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_kg_store_sqlite.py -k update_kg_node -v`
Expected: FAIL — `AttributeError: 'SQLiteStore' object has no attribute 'update_kg_node'`

**Step 3: Implement**

In `br8n/store/sqlite.py`, after `_merge_kg_node`:

```python
    async def update_kg_node(
        self,
        kb_id: str,
        node_id: str,
        *,
        properties: dict,
        grounded_in: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> None:
        """Overwrite payload in place (no merge). Re-indexes the vector if given."""
        if grounded_in is not None:
            self._conn.execute(
                "UPDATE kg_nodes SET properties = ?, grounded_in = ? WHERE id = ? AND kb_id = ?;",
                (json.dumps(properties), json.dumps(list(grounded_in)[-_MAX_GROUNDED:]),
                 node_id, kb_id),
            )
        else:
            self._conn.execute(
                "UPDATE kg_nodes SET properties = ? WHERE id = ? AND kb_id = ?;",
                (json.dumps(properties), node_id, kb_id),
            )
        if embedding is not None:
            self._conn.execute("DELETE FROM vec_kg_nodes WHERE node_id = ?;", (node_id,))
            self._conn.execute(
                "INSERT INTO vec_kg_nodes (node_id, embedding) VALUES (?, ?);",
                (node_id, serialize_float32(list(embedding))),
            )
        self._conn.commit()
```

**Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_kg_store_sqlite.py -k update_kg_node -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add br8n/store/sqlite.py tests/test_kg_store_sqlite.py
git commit -m "feat(store): SQLiteStore.update_kg_node overwrites node payload + re-embeds"
```

---

## Task 3: `update_kg_node` on SupabaseStore

**Files:**
- Modify: `br8n/store/supabase.py` (KG section, near `upsert_kg_nodes`)
- Test: `tests/test_store_supabase.py`

**Step 1: Write the failing test** (mirror the existing mocked-client pattern in that file)

Inspect `tests/test_store_supabase.py` for its fake-client fixture, then add:

```python
async def test_update_kg_node_issues_update_and_revec(fake_supabase_store):
    store, client = fake_supabase_store
    await store.update_kg_node(
        "kb1", "n1", properties={"body": "b", "version": 2},
        grounded_in=["f1"], embedding=[0.1] * 1536,
    )
    # asserts on the fake client: an update() to kg_nodes with the new properties,
    # and a match_kg_nodes/vector write path consistent with how upsert_kg_nodes
    # writes embeddings in this store. Follow the assertions style already used for
    # test_upsert_kg_nodes_* in this file.
```

> NOTE: match the exact fake-client assertion helpers this file already uses; do
> not invent a new mocking style. If the file has no KG tests yet, model the
> assertions on `test_store_supabase.py`'s existing `upsert_*` tests.

**Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_store_supabase.py -k update_kg_node -v`
Expected: FAIL — attribute/assertion error.

**Step 3: Implement** in `br8n/store/supabase.py`, mirroring `upsert_kg_nodes`'s table/embedding handling:

```python
    async def update_kg_node(
        self,
        kb_id: str,
        node_id: str,
        *,
        properties: dict,
        grounded_in: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> None:
        patch: dict = {"properties": properties}
        if grounded_in is not None:
            patch["grounded_in"] = list(grounded_in)
        if embedding is not None:
            patch["embedding"] = list(embedding)  # pgvector column on kg_nodes
        (
            self._client.table("kg_nodes")
            .update(patch)
            .eq("id", node_id)
            .eq("kb_id", kb_id)
            .execute()
        )
```

> Verify against this store's actual `upsert_kg_nodes`: if embeddings live in a
> separate table/RPC rather than a `kg_nodes.embedding` column, write the vector
> the same way that method does. Keep it consistent with the existing code path.

**Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_store_supabase.py -k update_kg_node -v`
Expected: PASS

**Step 5: Commit**

```bash
git add br8n/store/supabase.py tests/test_store_supabase.py
git commit -m "feat(store): SupabaseStore.update_kg_node overwrites node payload"
```

---

## Task 4: ConceptConfig

**Files:**
- Modify: `br8n/config.py` (add class after `ActivityConfig` ~line 170; wire into `Config` ~line 201)
- Test: `tests/test_config_concept.py` (create)

**Step 1: Write the failing test**

Create `tests/test_config_concept.py`:

```python
from br8n.config import get_config


def test_concept_config_defaults():
    c = get_config().concept
    assert c.synth_model
    assert 0.0 < c.reconcile_min_sim <= 1.0
    assert c.neighborhood_cap > 0
```

**Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_config_concept.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'concept'`

**Step 3: Implement**

In `br8n/config.py`, after `ActivityConfig`:

```python
class ConceptConfig(BaseModel):
    """Concept distillation — the synthesis tier above findings/activity.

    Runs select→synthesize→evaluate→reconcile over a KB's evidence to produce
    `concept` KG nodes. Best-effort and gated; never blocks capture/explore.
    """

    # Reserved home = the activity KB (concepts are personal-scoped, cross-KB).
    # Synthesis LLM (evidence cluster -> candidate concepts).
    synth_model: str = "anthropic/claude-sonnet-4.6"
    synth_fallback_model: str = "openai/gpt-5.4-mini"
    temperature: float = 0.0

    # Neighborhood selection caps.
    neighborhood_cap: int = 30          # max findings fed to one synthesis call
    max_concepts_per_pass: int = 6      # cap candidates from one synthesis call

    # Reconcile (Phase A: new vs reinforce).
    reconcile_min_sim: float = 0.78     # cosine: above => same concept, reinforce
    reconcile_fuzzy: float = 0.80       # SequenceMatcher claim-title ratio

    # Quality gate (reuses the exploration critic).
    enable_evaluation: bool = True
    min_confidence: float = 0.2
```

Then in `class Config` add:

```python
    concept: ConceptConfig = Field(default_factory=ConceptConfig)
```

**Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_config_concept.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add br8n/config.py tests/test_config_concept.py
git commit -m "feat(config): add ConceptConfig for the distillation tier"
```

---

## Task 5: Distillation models + `synthesize`

**Files:**
- Create: `br8n/knowledge_graph/distill.py`
- Test: `tests/test_distill_synthesize.py` (create)

**Step 1: Write the failing test** (stub the LLM; assert candidates are shaped + capped)

Create `tests/test_distill_synthesize.py`:

```python
import br8n.knowledge_graph.distill as d
from br8n.config import get_config


async def test_synthesize_returns_candidates(monkeypatch):
    async def fake_completion(**kw):
        return d.ConceptBatch(concepts=[
            d.ConceptCandidate(claim="X compounds Y", body="because Z", evidence=["f1", "f2"]),
        ])
    monkeypatch.setattr(d, "structured_completion", fake_completion)

    findings = [{"id": "f1", "title": "X", "content": "x details"},
                {"id": "f2", "title": "Y", "content": "y details"}]
    out = await d.synthesize(findings, get_config().concept)
    assert len(out) == 1
    assert out[0].claim == "X compounds Y"
    assert out[0].evidence == ["f1", "f2"]


async def test_synthesize_empty_findings_no_llm(monkeypatch):
    called = False
    async def fake_completion(**kw):
        nonlocal called; called = True
        return d.ConceptBatch(concepts=[])
    monkeypatch.setattr(d, "structured_completion", fake_completion)
    out = await d.synthesize([], get_config().concept)
    assert out == [] and called is False
```

**Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_distill_synthesize.py -v`
Expected: FAIL — module `br8n.knowledge_graph.distill` does not exist.

**Step 3: Implement** `br8n/knowledge_graph/distill.py` (models + synthesize only; reconcile/persist land in Task 6):

```python
"""Concept distillation — synthesize the concept tier from a KB's evidence.

    select findings ─► synthesize (LLM) ─► evaluate (critic) ─► reconcile ─► upsert

Concepts are `kg_nodes type='concept'` living in the per-org activity KB, evidence
via `grounded_in`, bound to activity via `about` edges. Phase A: new vs reinforce.
Best-effort and gated by BR8N_DISTILL_KG / BR8N_DISTILL_LLM.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from br8n.clients.ai_gateway import structured_completion
from br8n.config import ConceptConfig

logger = logging.getLogger(__name__)

_SNIPPET_CHARS = 600


class ConceptCandidate(BaseModel):
    claim: str = Field(description="Canonical one-line claim (the concept's identity)")
    body: str = Field(default="", description="Synthesized explanation in prose")
    evidence: list[str] = Field(default_factory=list, description="Finding ids justifying it")


class ConceptBatch(BaseModel):
    concepts: list[ConceptCandidate] = Field(default_factory=list)


_SYNTH_SYSTEM = (
    "You distil research findings into higher-order CONCEPTS. Given numbered "
    "findings (id, title, content), produce concepts that each: state ONE "
    "non-obvious claim a person would want to remember, in a canonical one-line "
    "`claim`; explain it in `body`; and list the finding ids that justify it in "
    "`evidence`. Synthesize ACROSS findings — a concept that restates a single "
    "finding is not a concept. Be specific and calibrated; emit fewer, denser "
    "concepts rather than many vague ones."
)


def _catalogue(findings: list[dict]) -> str:
    lines = []
    for f in findings:
        body = str(f.get("content") or "")[:_SNIPPET_CHARS]
        lines.append(f"[{f.get('id')}] {f.get('title','')}\n{body}")
    return "\n\n".join(lines)


async def synthesize(findings: list[dict], cfg: ConceptConfig) -> list[ConceptCandidate]:
    """One structured LLM call over an evidence cluster -> candidate concepts.
    Returns [] without calling the LLM when there are no findings."""
    if not findings:
        return []
    batch: ConceptBatch = await structured_completion(
        model=cfg.synth_model,
        response_format=ConceptBatch,
        system=_SYNTH_SYSTEM,
        user=_catalogue(findings[: cfg.neighborhood_cap]),
        temperature=cfg.temperature,
        fallback_model=cfg.synth_fallback_model,
    )
    return batch.concepts[: cfg.max_concepts_per_pass]
```

**Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_distill_synthesize.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add br8n/knowledge_graph/distill.py tests/test_distill_synthesize.py
git commit -m "feat(distill): concept models + synthesize over an evidence cluster"
```

---

## Task 6: `reconcile` (pure: new vs reinforce)

**Files:**
- Modify: `br8n/knowledge_graph/distill.py`
- Test: `tests/test_distill_reconcile.py` (create)

**Step 1: Write the failing test** (pure decision, no IO)

Create `tests/test_distill_reconcile.py`:

```python
from br8n.config import get_config
from br8n.knowledge_graph.distill import ConceptCandidate, reconcile_action


def _cfg():
    return get_config().concept


def test_reconcile_new_when_no_neighbor():
    cand = ConceptCandidate(claim="fresh idea", evidence=["f1"])
    action = reconcile_action(cand, nearest=None, similarity=0.0, cfg=_cfg())
    assert action.kind == "new"


def test_reconcile_reinforce_on_high_similarity():
    cand = ConceptCandidate(claim="x compounds", evidence=["f2"])
    nearest = {"id": "n1", "label": "x compounds"}
    action = reconcile_action(cand, nearest=nearest, similarity=0.95, cfg=_cfg())
    assert action.kind == "reinforce"
    assert action.node_id == "n1"


def test_reconcile_new_when_similar_vector_but_different_claim():
    # cosine just above threshold but claims are unrelated text -> stay separate
    cand = ConceptCandidate(claim="totally different topic", evidence=["f3"])
    nearest = {"id": "n1", "label": "x compounds y in systems"}
    action = reconcile_action(cand, nearest=nearest, similarity=0.79, cfg=_cfg())
    assert action.kind == "new"
```

**Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_distill_reconcile.py -v`
Expected: FAIL — `cannot import name 'reconcile_action'`.

**Step 3: Implement** — append to `br8n/knowledge_graph/distill.py`:

```python
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass
class ReconcileAction:
    kind: str               # "new" | "reinforce"
    node_id: str | None = None


def _claim_similar(a: str, b: str, threshold: float) -> bool:
    if not a or not b:
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def reconcile_action(
    cand: ConceptCandidate,
    *,
    nearest: dict | None,
    similarity: float,
    cfg: ConceptConfig,
) -> ReconcileAction:
    """Phase A: decide new vs reinforce. A candidate reinforces the nearest existing
    concept only when BOTH the vector is close (>= reconcile_min_sim) AND the claim
    text fuzzy-matches (>= reconcile_fuzzy) — guarding against semantically-near but
    distinct claims. Otherwise it's a new concept. (refine/contradict: Phase C.)"""
    if (
        nearest
        and similarity >= cfg.reconcile_min_sim
        and _claim_similar(cand.claim, nearest.get("label", ""), cfg.reconcile_fuzzy)
    ):
        return ReconcileAction(kind="reinforce", node_id=nearest["id"])
    return ReconcileAction(kind="new")
```

**Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_distill_reconcile.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add br8n/knowledge_graph/distill.py tests/test_distill_reconcile.py
git commit -m "feat(distill): pure reconcile_action (new vs reinforce)"
```

---

## Task 7: `distill_kb` orchestrator (select → synth → evaluate → reconcile → upsert)

**Files:**
- Modify: `br8n/knowledge_graph/distill.py`
- Test: `tests/test_distill_flow.py` (create) — uses a real in-memory `SQLiteStore`, stubs only the LLM.

**Step 1: Write the failing test**

Create `tests/test_distill_flow.py`:

```python
import pytest

import br8n.knowledge_graph.distill as d
from br8n.store import SQLiteStore

DIM = 1536


def _vec(seed):
    v = list(seed) + [0.0] * (DIM - len(seed))
    return v[:DIM]


@pytest.fixture
def store():
    return SQLiteStore(":memory:")


async def _seed_findings(store, kb_id):
    # two findings in the activity KB's evidence space (use the findings table)
    await store.insert_findings([
        {"org_id": "local", "kb_id": kb_id, "project_id": "p", "title": "X",
         "content": "x details", "category": "general", "confidence": 0.7,
         "embedding": _vec([1.0, 0.0])},
        {"org_id": "local", "kb_id": kb_id, "project_id": "p", "title": "Y",
         "content": "y details", "category": "general", "confidence": 0.7,
         "embedding": _vec([0.9, 0.1])},
    ])


async def test_distill_kb_creates_concept_with_evidence(monkeypatch, store):
    kb = "akb"
    await _seed_findings(store, kb)

    async def fake_synth(findings, cfg):
        return [d.ConceptCandidate(claim="X and Y compound", body="why", evidence=["does-not-matter"])]
    monkeypatch.setattr(d, "synthesize", fake_synth)
    monkeypatch.setattr(d, "_embed_claims", lambda claims: [_vec([0.0, 1.0]) for _ in claims])

    n = await d.distill_kb(store, org_id="local", kb_id=kb)
    assert n["concepts_created"] == 1

    concepts = store.list_kg_nodes(kb, type="concept")
    assert len(concepts) == 1
    assert concepts[0]["label"] == "X and Y compound"
    # evidence was bound from the selected findings (ids real, not the stub's)
    assert concepts[0]["grounded_in"]


async def test_distill_kb_reinforces_on_second_pass(monkeypatch, store):
    kb = "akb"
    await _seed_findings(store, kb)

    async def fake_synth(findings, cfg):
        return [d.ConceptCandidate(claim="X and Y compound", body="v", evidence=[])]
    monkeypatch.setattr(d, "synthesize", fake_synth)
    monkeypatch.setattr(d, "_embed_claims", lambda claims: [_vec([0.0, 1.0]) for _ in claims])

    await d.distill_kb(store, org_id="local", kb_id=kb)
    await d.distill_kb(store, org_id="local", kb_id=kb)  # same claim again

    concepts = store.list_kg_nodes(kb, type="concept")
    assert len(concepts) == 1   # reinforced, not duplicated
    assert concepts[0]["properties"].get("version", 1) >= 2
```

> Confirm `insert_findings` accepts an `embedding` key and `list_kg_nodes` returns
> `properties`/`grounded_in` decoded (it does — see `tests/test_kg_store_sqlite.py`).
> If `insert_findings`' row shape differs, match the shape used in
> `tests/test_store_sqlite.py`.

**Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_distill_flow.py -v`
Expected: FAIL — `distill_kb` / `_embed_claims` not defined.

**Step 3: Implement** — append to `br8n/knowledge_graph/distill.py`:

```python
from br8n.clients.embeddings import embed_batch
from br8n.exploration.merger import blended_confidence
from br8n.store import Store


async def _embed_claims(claims: list[str]) -> list[list[float]]:
    """Seam so tests can stub embeddings."""
    return await embed_batch(claims) if claims else []


async def _select_findings(store: Store, kb_id: str, cfg: ConceptConfig) -> list[dict]:
    """Phase A neighborhood = the KB's most recent findings (capped)."""
    res = store.list_findings(kb_id, limit=cfg.neighborhood_cap)
    rows = res.get("findings", res) if isinstance(res, dict) else res
    # list_findings omits content; fetch bodies for the synthesis catalogue.
    return [store.get_finding(kb_id, r["id"]) for r in rows]


async def distill_kb(store: Store, *, org_id: str, kb_id: str) -> dict:
    """Run one distillation pass over `kb_id`. Returns counts. Best-effort caller
    wraps this; here we let exceptions propagate so tests can assert."""
    cfg = get_config().concept
    findings = await _select_findings(store, kb_id, cfg)
    if not findings:
        return {"concepts_created": 0, "concepts_reinforced": 0}

    candidates = await synthesize(findings, cfg)
    if not candidates:
        return {"concepts_created": 0, "concepts_reinforced": 0}

    # Bind evidence to the REAL selected finding ids (the LLM's echoed ids are
    # advisory; ground in what we actually fed it).
    evidence_ids = [f["id"] for f in findings]

    embeddings = await _embed_claims([c.claim for c in candidates])
    created = reinforced = 0
    for i, cand in enumerate(candidates):
        emb = embeddings[i] if i < len(embeddings) else None
        nearest, sim = None, 0.0
        if emb is not None:
            hits = await store.match_kg_nodes(
                kb_id, emb, match_count=1, min_similarity=cfg.reconcile_min_sim
            )
            hits = [h for h in hits if h.get("type") == "concept"]
            if hits:
                nearest, sim = hits[0], hits[0]["similarity"]

        action = reconcile_action(cand, nearest=nearest, similarity=sim, cfg=cfg)
        if action.kind == "reinforce" and action.node_id:
            existing = next(
                (n for n in store.list_kg_nodes(kb_id, type="concept")
                 if n["id"] == action.node_id), None,
            )
            props = dict((existing or {}).get("properties") or {})
            prev_ev = list((existing or {}).get("grounded_in") or [])
            merged_ev = list(dict.fromkeys([*prev_ev, *evidence_ids]))
            props["version"] = int(props.get("version", 1)) + 1
            props["body"] = cand.body or props.get("body", "")
            props["confidence"] = blended_confidence(len(merged_ev), 1.0)
            await store.update_kg_node(
                kb_id, action.node_id,
                properties=props, grounded_in=merged_ev, embedding=emb,
            )
            reinforced += 1
        else:
            await store.upsert_kg_nodes(kb_id, [{
                "org_id": org_id, "type": "concept", "label": cand.claim,
                "properties": {
                    "body": cand.body, "version": 1, "status": "active",
                    "confidence": blended_confidence(len(evidence_ids), 1.0),
                    "source_kbs": [kb_id],
                },
                "grounded_in": evidence_ids, "embedding": emb,
            }])
            created += 1

    return {"concepts_created": created, "concepts_reinforced": reinforced}
```

> The critic-gate (`evaluate_findings`-style) and `about` edges are added in Task 8.

**Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_distill_flow.py -v`
Expected: PASS (2 tests). If `list_findings`/`get_finding` row shapes differ from
the assumption, adjust `_select_findings` to the real shape and re-run.

**Step 5: Commit**

```bash
git add br8n/knowledge_graph/distill.py tests/test_distill_flow.py
git commit -m "feat(distill): distill_kb orchestrator (create + reinforce concepts)"
```

---

## Task 8: Bind concepts to activity via `about` edges + critic gate

**Files:**
- Modify: `br8n/knowledge_graph/distill.py`
- Test: `tests/test_distill_flow.py` (extend)

**Step 1: Write the failing test**

Add to `tests/test_distill_flow.py`:

```python
async def test_distill_binds_about_edge_to_existing_activity_node(monkeypatch, store):
    kb = "akb"
    await _seed_findings(store, kb)
    # an activity 'task' node grounded in finding f-real-0 (the first selected id)
    findings = await d._select_findings(store, get_config().concept, kb_id=kb) \
        if False else None  # see note below

    async def fake_synth(findings, cfg):
        return [d.ConceptCandidate(claim="bound concept", body="b", evidence=[])]
    monkeypatch.setattr(d, "synthesize", fake_synth)
    monkeypatch.setattr(d, "_embed_claims", lambda claims: [_vec([0.0, 1.0]) for _ in claims])

    # create a task node grounded in one of the KB's findings
    ev_ids = [f["id"] for f in await d._select_findings(store, kb, get_config().concept)]
    await store.upsert_kg_nodes(kb, [{
        "org_id": "local", "type": "task", "label": "do the thing",
        "properties": {}, "grounded_in": [ev_ids[0]], "embedding": None,
    }])

    await d.distill_kb(store, org_id="local", kb_id=kb)

    sub = store.get_kg_subgraph(kb, node_cap=100, edge_cap=200)
    assert any(e["relation"] == "about" for e in sub["edges"])
```

> NOTE: align `_select_findings`' call signature in the test with its real one
> (`_select_findings(store, kb_id, cfg)`); the `if False` line above is a
> placeholder to delete — fetch `ev_ids` via the real signature.

**Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_distill_flow.py -k about_edge -v`
Expected: FAIL — no `about` edges produced.

**Step 3: Implement** — in `distill_kb`, after a concept node id is known (both
branches), add edge-binding, and add the optional critic gate before the loop:

```python
# (near top of distill_kb, after candidates is built)
from br8n.exploration.evaluator import evaluate_findings  # reuse the critic
# Optional: gate candidates by turning them into lightweight Finding-likes is
# overkill; instead keep Phase A simple — confidence gating happens via
# blended_confidence + cfg.min_confidence at read time. (Critic gate deferred to
# Phase B once triggers add volume.)  <-- DELETE the import if not used.
```

Edge binding helper + call (append to module, and invoke for each created/reinforced concept id):

```python
def _activity_nodes_for_evidence(store: Store, kb_id: str, evidence_ids: list[str]) -> list[str]:
    """Activity node ids (task/file/repo) whose grounded_in intersects the evidence."""
    ev = set(evidence_ids)
    out: list[str] = []
    for typ in ("task", "file", "repo"):
        for n in store.list_kg_nodes(kb_id, type=typ, limit=500):
            if ev & set(n.get("grounded_in") or []):
                out.append(n["id"])
    return out


async def _bind_about(store: Store, org_id: str, kb_id: str, concept_id: str,
                      evidence_ids: list[str]) -> None:
    targets = _activity_nodes_for_evidence(store, kb_id, evidence_ids)
    if not targets:
        return
    await store.upsert_kg_edges(kb_id, [{
        "org_id": org_id, "source_node_id": concept_id, "target_node_id": t,
        "relation": "about", "properties": {}, "grounded_in": evidence_ids,
    } for t in targets])
```

In both branches of the loop, capture the concept id and call
`await _bind_about(store, org_id, kb_id, concept_id, merged_ev_or_evidence_ids)`.
For the `new` branch the id is `ids[0]` from `upsert_kg_nodes`; for `reinforce`
it's `action.node_id`.

**Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_distill_flow.py -v`
Expected: PASS (all flow tests, incl. `about_edge`).

**Step 5: Run the full suite + commit**

```bash
.venv/bin/pytest tests/ -q
git add br8n/knowledge_graph/distill.py tests/test_distill_flow.py
git commit -m "feat(distill): bind concepts to activity via about edges"
```

---

## Phase A done-when checklist

- [ ] `update_kg_node` on protocol + both stores, overwrites payload + re-embeds.
- [ ] `ConceptConfig` wired into `get_config().concept`.
- [ ] `distill.py`: `synthesize` (LLM) + pure `reconcile_action` + `distill_kb`.
- [ ] A manual `distill_kb(...)` over a KB's findings creates `concept` nodes with
      `grounded_in` evidence and `about` edges; a second pass on the same claim
      **reinforces** (version bump), not duplicates.
- [ ] Full `pytest tests/` green.

## Not in Phase A (next plans)

- **Phase B** — triggers: chain `distill_kb` off `api/capture.py` (after
  `schedule_activity_update`) and `api/explore.py` (after persist), debounced +
  gated (`BR8N_DISTILL_KG`/`_LLM`), fire-and-forget. Add the critic gate here
  once volume justifies it.
- **Phase C** — `band_concepts` + `<concepts>` in `render_preamble`; `/v1/context`
  + `br8n_context`; re-point resume/search; `refines`/`contradicts` reconciliation.
- **Phase D** — `/br8n:distill` skill + `br8n_distill` MCP tool.

### Carry-over from the Phase A final review (MUST revisit before the Phase B trigger)

Two items the final code review surfaced. Neither blocks Phase A's manual driver,
but both must be handled when `distill_kb` is wired into a fire-and-forget
post-capture/explore trigger:

1. **Fire-and-forget error swallow.** `distill_kb` currently lets exceptions
   propagate (correct for the manual/test driver). Before dropping it into
   `asyncio.create_task`, wrap the call the way `activity.py::_run_activity_update`
   does (`except Exception: logger.exception(...)`) so a distillation failure can
   never break a capture/explore. The module's `logger` is already in place for this.
2. **Confidence saturates to ~1.0.** `blended_confidence(len(merged_ev), 1.0)` uses
   the *whole selected cluster* (up to `neighborhood_cap=30` findings) as the source
   count, so `1 − 0.6^30 ≈ 1.0` for essentially every concept, and the `quality`
   multiplier is hardcoded `1.0` (`enable_evaluation`/`min_confidence` in
   `ConceptConfig` are defined but unused). Fix when the Phase-C critic lands: feed
   the critic's per-concept `quality` into `blended_confidence`, and base the source
   count on the concept's *actual* corroborating evidence (e.g. the LLM's per-concept
   `cand.evidence` validated against real ids) rather than the full cluster.
