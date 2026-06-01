"""Concept distillation — synthesize the concept tier from a KB's evidence.

    select findings -> synthesize (LLM) -> evaluate (critic) -> reconcile -> upsert

Concepts are `kg_nodes type='concept'` living in the per-org activity KB, evidence
via `grounded_in`, bound to activity via `about` edges. Phase A: new vs reinforce.
Best-effort and gated by BRAIN2_DISTILL_KG / BRAIN2_DISTILL_LLM.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from brain2.clients.ai_gateway import structured_completion
from brain2.clients.embeddings import embed_batch
from brain2.config import ConceptConfig, get_config
from brain2.exploration.merger import blended_confidence
from brain2.store import Store

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


# --- orchestration -----------------------------------------------------------


async def _embed_claims(claims: list[str]) -> list[list[float]]:
    """Seam so tests can stub embeddings."""
    return await embed_batch(claims) if claims else []


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


async def _select_findings(store: Store, kb_id: str, cfg: ConceptConfig) -> list[dict]:
    """Phase A neighborhood = the KB's most recent findings (capped). Returns rows
    WITH content (list_findings omits bodies, so fetch each via get_finding)."""
    res = store.list_findings(kb_id, limit=cfg.neighborhood_cap)
    rows = res["findings"] if isinstance(res, dict) else res
    # If list rows already include 'content', use them directly; else fetch bodies.
    if rows and "content" in rows[0]:
        return list(rows)
    return [store.get_finding(kb_id, r["id"]) for r in rows]


async def distill_kb(store: Store, *, org_id: str, kb_id: str) -> dict:
    """Run one distillation pass over kb_id. Returns counts.

    select recent findings -> synthesize candidates -> for each, find the nearest
    existing `concept` node semantically -> reconcile -> create a NEW concept or
    REINFORCE an existing one (version bump, evidence union, refreshed body/conf)."""
    cfg = get_config().concept
    findings = await _select_findings(store, kb_id, cfg)
    if not findings:
        return {"concepts_created": 0, "concepts_reinforced": 0}

    candidates = await synthesize(findings, cfg)
    if not candidates:
        return {"concepts_created": 0, "concepts_reinforced": 0}

    evidence_ids = [f["id"] for f in findings]   # ground in what we actually fed in

    res = _embed_claims([c.claim for c in candidates])
    embeddings = await res if inspect.isawaitable(res) else res

    created = reinforced = 0
    for i, cand in enumerate(candidates):
        emb = embeddings[i] if i < len(embeddings) else None
        # Widen the candidate set (a non-concept activity node can be the rank-1
        # neighbour), then pick the nearest CONCEPT.
        nearest, sim = None, 0.0
        if emb is not None:
            hits = await store.match_kg_nodes(
                kb_id, emb, match_count=5, min_similarity=cfg.reconcile_min_sim
            )
            concept_hits = [h for h in hits if h.get("type") == "concept"]
            if concept_hits:
                nearest, sim = concept_hits[0], concept_hits[0]["similarity"]

        action = reconcile_action(cand, nearest=nearest, similarity=sim, cfg=cfg)
        if action.kind == "reinforce" and action.node_id:
            # Read the full target by id — list_kg_nodes is capped + recency-windowed,
            # so an older concept would scan to None and silently wipe its body/version.
            # Fall back to `nearest` (carries properties), so the body is never zeroed.
            existing = store.get_kg_node(kb_id, action.node_id) or nearest or {}
            props = dict(existing.get("properties") or {})
            prev_ev = list(existing.get("grounded_in") or [])
            merged_ev = list(dict.fromkeys([*prev_ev, *evidence_ids]))
            props["version"] = int(props.get("version", 1)) + 1
            props["body"] = cand.body or props.get("body", "")
            props["confidence"] = blended_confidence(len(merged_ev), 1.0)
            await store.update_kg_node(
                kb_id, action.node_id,
                properties=props, grounded_in=merged_ev, embedding=emb,
            )
            await _bind_about(store, org_id, kb_id, action.node_id, merged_ev)
            reinforced += 1
        else:
            ids = await store.upsert_kg_nodes(kb_id, [{
                "org_id": org_id, "type": "concept", "label": cand.claim,
                "properties": {
                    "body": cand.body, "version": 1, "status": "active",
                    "confidence": blended_confidence(len(evidence_ids), 1.0),
                    "source_kbs": [kb_id],
                },
                "grounded_in": evidence_ids, "embedding": emb,
            }])
            await _bind_about(store, org_id, kb_id, ids[0], evidence_ids)
            created += 1

    return {"concepts_created": created, "concepts_reinforced": reinforced}
