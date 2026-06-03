"""Schema-drift detector — does the KB's graph still fit its ontology?

    kg_stats().by_type + intent schema ──► residual ratio ──► DriftVerdict
                                                              (cold_start | drift | ok)

The trigger half of the self-maintaining loop: a cheap, best-effort check that
decides *when* to surface the KG-schema wizard. It does **not** run the wizard —
it raises a flag the surfacing path (a turn-boundary offer) acts on.

It free-rides on the type distribution the built graph already carries
(``kg_stats().by_type``) — no extra LLM call, no extra pass. A node is a
**residual** when the extractor couldn't place it in the ontology: its type is
``"other"``, or (with a schema set) a type the schema doesn't declare. Residuals
are exactly the signal the soft-schema extractor keeps instead of dropping
(see ``extractor._schema_block``), so the residual cluster IS the seed the wizard
reshapes around.

Two fire modes (the two triggers the product names):
  - **cold_start** — no schema set yet and the graph crossed ``cold_start_min_nodes``
    ("enough collected to propose a first schema").
  - **drift** — a schema is set and the residual ratio crossed ``drift_ratio`` with
    at least ``drift_floor`` residual nodes ("reality moved past the ontology").

Gating — "offer once, then go quiet" (the non-blocking philosophy):
  - cold_start debounces on the existing ``init_offered`` stamp;
  - drift re-arms only once residual grows by ``rearm_delta`` beyond the count
    stamped at the last offer, so a steady "no" stays quiet but intensifying drift
    can eventually re-ask.

Best-effort: any failure yields ``mode="ok"`` / ``should_offer=False`` — never raises.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from brain2.config import DriftConfig
from brain2.knowledge_graph.models import KGSchema
from brain2.store import Store

logger = logging.getLogger(__name__)

# The extractor's catch-all type for entities that didn't fit the ontology.
_RESIDUAL_TYPE = "other"


@dataclass
class DriftVerdict:
    """The detector's read on one KB's graph. ``offer_line`` is the ready-to-show,
    one-line turn-boundary offer (``None`` unless ``should_offer``)."""

    mode: str  # "cold_start" | "drift" | "ok" | "empty"
    node_count: int = 0
    residual: int = 0
    ratio: float = 0.0
    schema_version: int | None = None
    residual_types: list[dict] = field(default_factory=list)  # [{type, count}], desc by count
    should_offer: bool = False
    offer_line: str | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "node_count": self.node_count,
            "residual": self.residual,
            "ratio": round(self.ratio, 3),
            "schema_version": self.schema_version,
            "residual_types": self.residual_types,
            "should_offer": self.should_offer,
            "offer_line": self.offer_line,
        }


def residual_breakdown(by_type: dict[str, int], schema: KGSchema | None) -> tuple[int, list[dict]]:
    """Split a graph's ``by_type`` counts into the residual (off-ontology) share.

    Residual = type ``"other"``, or — when a schema is set — any type the schema
    does not declare. With no schema, only ``"other"`` counts (everything else is
    just un-curated, not *off*-curated). Returns ``(residual_total, [{type, count}])``
    sorted by count desc."""
    names = {nt.name.strip().lower() for nt in schema.node_types} if schema else set()
    residual: list[dict] = []
    for raw_type, count in (by_type or {}).items():
        if not count:
            continue
        t = (raw_type or "").strip().lower()
        is_residual = t == _RESIDUAL_TYPE or (schema is not None and t not in names)
        if is_residual:
            residual.append({"type": raw_type or _RESIDUAL_TYPE, "count": int(count)})
    residual.sort(key=lambda r: (r["count"], r["type"]), reverse=True)
    return sum(r["count"] for r in residual), residual


def _cluster_str(residual_types: list[dict], top: int = 3) -> str:
    """Human label for the residual cluster, e.g. ``deployment, rollback, incident``."""
    names = [r["type"] for r in residual_types[:top] if r.get("type")]
    return ", ".join(names) or "unplaced entities"


def _load_intent(store: Store, kb_id: str) -> tuple[KGSchema | None, int | None]:
    """Best-effort read of the active intent schema → ``(schema, version)``.

    Returns ``(None, None)`` when unset, and ``(None, version)`` when a stored
    schema is malformed (treated as no usable schema — the cold-start path)."""
    try:
        raw = store.get_kg_intent(kb_id)
    except Exception:  # noqa: BLE001 — best-effort; a read error must not raise
        return None, None
    if not raw or not raw.get("schema"):
        return None, None
    version = raw.get("version")
    try:
        return KGSchema.model_validate(raw["schema"]), version
    except Exception:  # noqa: BLE001 — a malformed stored schema → cold-start, never raise
        logger.warning("drift: kb %s has a malformed intent schema; treating as unset", kb_id)
        return None, version


def assess_drift(
    store: Store,
    kb_id: str,
    cfg: DriftConfig,
    *,
    init_offered: bool = False,
    drift_marker: int = 0,
) -> DriftVerdict:
    """Decide whether to offer the schema wizard for ``kb_id`` — and why.

    ``init_offered`` / ``drift_marker`` are the debounce inputs (the caller reads
    them from the Store and passes them in, keeping this function pure over its
    inputs and trivially testable). ``drift_marker`` is the residual count stamped
    at the last drift offer (0 = never offered)."""
    try:
        stats = store.kg_stats(kb_id)
    except Exception:  # noqa: BLE001 — best-effort: a stats failure means "do nothing visible"
        logger.warning("drift: kg_stats failed for kb=%s", kb_id, exc_info=True)
        return DriftVerdict(mode="ok")

    total = int(stats.get("node_count") or 0)
    by_type = stats.get("by_type") or {}
    intent, schema_version = _load_intent(store, kb_id)

    # Too small to judge — neither enough to seed a schema nor to call drift.
    if total < cfg.min_nodes:
        return DriftVerdict(mode="empty", node_count=total, schema_version=schema_version)

    residual, residual_types = residual_breakdown(by_type, intent)
    ratio = (residual / total) if total else 0.0

    # --- cold-start: enough collected, no usable schema yet ------------------
    if intent is None:
        if total >= cfg.cold_start_min_nodes:
            should = not init_offered
            line = (
                f"brain2 has collected {total} graph nodes and no schema yet — "
                f"design one to organize them? `/brain2:schema`"
            )
            return DriftVerdict(
                mode="cold_start", node_count=total, residual=residual, ratio=ratio,
                schema_version=None, residual_types=residual_types,
                should_offer=should, offer_line=line if should else None,
            )
        return DriftVerdict(mode="ok", node_count=total, residual=residual, ratio=ratio)

    # --- drift: schema set, but reality moved past it ------------------------
    drifting = ratio >= cfg.drift_ratio and residual >= cfg.drift_floor
    if drifting:
        # First drift (no marker) fires; after a stamp, require fresh growth.
        should = residual >= drift_marker + cfg.rearm_delta if drift_marker > 0 else True
        pct = round(ratio * 100)
        line = (
            f"Your knowledge graph has drifted: {residual}/{total} nodes ({pct}%) "
            f"don't fit schema v{schema_version} (mostly {_cluster_str(residual_types)}) "
            f"— reshape it? `/brain2:schema`"
        )
        return DriftVerdict(
            mode="drift", node_count=total, residual=residual, ratio=ratio,
            schema_version=schema_version, residual_types=residual_types,
            should_offer=should, offer_line=line if should else None,
        )

    return DriftVerdict(
        mode="ok", node_count=total, residual=residual, ratio=ratio,
        schema_version=schema_version, residual_types=residual_types,
    )
