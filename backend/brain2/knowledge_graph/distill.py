"""Concept distillation — synthesize the concept tier from a KB's evidence.

    select findings -> synthesize (LLM) -> evaluate (critic) -> reconcile -> upsert

Concepts are `kg_nodes type='concept'` living in the per-org activity KB, evidence
via `grounded_in`, bound to activity via `about` edges. Phase A: new vs reinforce.
Best-effort and gated by BRAIN2_DISTILL_KG / BRAIN2_DISTILL_LLM.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from brain2.clients.ai_gateway import structured_completion
from brain2.config import ConceptConfig

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
