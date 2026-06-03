"""The curated doc-tree distiller — note Findings → rendered ``.brain2/docs/`` tree.

    note appended ─► schedule_distill ─► (debounce) ─► run_distill
                                                       ├─ _infer_topics (gated LLM)
                                                       ├─ plan_layout   (pure)
                                                       └─ write curated markdown tree

The doc tree is **rendered output only** — it is NEVER re-ingested as Findings (that
would distill its own output in a loop). Folder structure is INFERRED from note content
(flat until enough notes accumulate, then clustered by topic); a user KG-intent schema,
if set, overrides the inferred folders. Population is debounced + fire-and-forget +
best-effort: a distill failure never breaks the user's session.

Mirrors ``knowledge_graph/activity.py``:
- ``_infer_topics`` mirrors ``_task_label`` — same ``BRAIN2_LIVING_DOCS_LLM`` env gate,
  same ``structured_completion`` client + model-config source, deterministic fallback.
- ``schedule_distill`` mirrors ``schedule_activity_update`` — module-level ``_BG_TASKS``
  set with ``add_done_callback(_BG_TASKS.discard)``, gated by ``BRAIN2_LIVING_DOCS``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from brain2.agent.state import TenantContext
from brain2.clients.ai_gateway import structured_completion
from brain2.config import get_config
from brain2.livingdocs.paths import DocPaths, ensure_layout
from brain2.livingdocs.state import load_state, save_state, should_distill
from brain2.store import get_store

logger = logging.getLogger(__name__)


# --- slugging ----------------------------------------------------------------

def _slug(text: str) -> str:
    """Lowercase, non-alnum→'-', collapsed — for file basenames and folder names."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:48]


# --- pure, deterministic layout planning -------------------------------------

def _match_schema_folder(topic: str | None, schema: list[str]) -> str:
    """Map a free-text topic to the nearest schema folder, deterministically.

    Exact case-insensitive match wins; else substring match either direction;
    else "" (flat). Result is always a subset of ``schema ∪ {""}``."""
    if not topic:
        return ""
    t = topic.strip().lower()
    if not t:
        return ""
    for name in schema:
        if t == name.strip().lower():
            return name
    for name in schema:
        n = name.strip().lower()
        if n and (n in t or t in n):
            return name
    return ""


def plan_layout(
    notes: list[dict], *, cluster_min_notes: int, schema: list[str] | None
) -> list[dict]:
    """Decide each note's curated folder. PURE + deterministic — no LLM, no I/O.

    Each input note dict carries at least ``"title"`` and ``"topic"`` (topic may be
    None). Returns one entry per note: ``{"folder", "title", "topic", "note": <orig>}``.

    - Below ``cluster_min_notes``: everything is flat (``folder=""``).
    - At/above the threshold: group by ``topic`` (None → flat; else a slugified topic
      folder). If ``schema`` is given, each note maps to the nearest schema folder
      instead (see ``_match_schema_folder``), so folders ⊆ ``schema ∪ {""}``.
    """
    flat = len(notes) < cluster_min_notes
    layout: list[dict] = []
    for note in notes:
        topic = note.get("topic")
        if flat:
            folder = ""
        elif schema is not None:
            folder = _match_schema_folder(topic, schema)
        elif topic:
            folder = _slug(topic)
        else:
            folder = ""
        layout.append({
            "folder": folder,
            "title": note.get("title", ""),
            "topic": topic,
            "note": note,
        })
    return layout


# --- gated LLM topic inference -----------------------------------------------

class _Topics(BaseModel):
    topics: list[str] = Field(
        default_factory=list,
        description="One SHORT topic (1-3 words) per input note, same order",
    )


_TOPIC_SYSTEM = (
    "You tag developer session notes with a SHORT topic for foldering.\n"
    "Given a numbered list of notes (title + content), return one topic per note,\n"
    "in the SAME ORDER. Rules: 1-3 words, lowercase, no punctuation; group related\n"
    "notes under the SAME topic word; prefer a stable domain noun (e.g. 'auth',\n"
    "'ui', 'storage') over incidental detail. Return JSON {\"topics\": [\"...\", ...]}."
)


def _topic_prompt(notes: list[dict]) -> str:
    lines = []
    for i, n in enumerate(notes):
        title = (n.get("title") or "").strip()
        content = (n.get("content") or "").strip().replace("\n", " ")
        lines.append(f"{i + 1}. {title} — {content[:300]}")
    return "\n".join(lines)


async def _infer_topics(notes: list[dict]) -> list[str | None]:
    """Tag each note with a short topic via the LLM, in order. Gated + best-effort.

    Mirrors ``activity._task_label``: ``BRAIN2_LIVING_DOCS_LLM=0`` (or any failure /
    parse mismatch) falls back to ``[None] * len(notes)`` → a flat layout. One batched
    call returns a topic per note. Never raises."""
    if not notes:
        return []
    if os.getenv("BRAIN2_LIVING_DOCS_LLM", "1") == "0":
        return [None] * len(notes)
    cfg = get_config().living_docs
    try:
        result = await structured_completion(
            model=cfg.distill_model,
            response_format=_Topics,
            system=_TOPIC_SYSTEM,
            user=_topic_prompt(notes),
            temperature=cfg.temperature,
            fallback_model=cfg.distill_fallback_model,
            use_json_schema=False,
        )
        topics = result.topics or []
    except Exception as exc:  # noqa: BLE001 — topic inference is best-effort
        logger.warning("living-docs topic inference failed (%s); flat layout", exc)
        return [None] * len(notes)
    # Align length to notes: pad with None, truncate extras, normalize blanks→None.
    out: list[str | None] = []
    for i in range(len(notes)):
        t = topics[i].strip() if i < len(topics) and isinstance(topics[i], str) else ""
        out.append(t or None)
    return out


# --- schema (user-set KG intent) → folder names ------------------------------

def _schema_folders(store, kb_id: str) -> list[str] | None:
    """The KB's KG-intent node-type names as override folders, or None. Best-effort."""
    try:
        raw = store.get_kg_intent(kb_id)
        if not raw:
            return None
        from brain2.knowledge_graph.models import KGSchema

        schema = KGSchema.model_validate(raw.get("schema") or raw)
        names = [(nt.name or "").strip() for nt in schema.node_types]
        names = [n for n in names if n]
        return names or None
    except Exception:  # noqa: BLE001 — no schema / malformed → infer instead
        return None


# --- curated rendering -------------------------------------------------------

def _render(title: str, content: str) -> str:
    """A curated doc file: an H1 title lead + the note content (v1 = light rendering)."""
    body = (content or "").strip("\n")
    if not body.lstrip().startswith("# "):
        body = f"# {title}\n\n{body}"
    return body + "\n"


# --- distill (best-effort) ---------------------------------------------------

async def run_distill(ctx: TenantContext, *, project_path: str, kb: str) -> dict:
    """Distill the KB's note Findings into the curated ``.brain2/docs/`` tree.

    Loads ``category="note"`` Findings, infers a topic per note (gated LLM), plans a
    deterministic folder layout (schema-overridden if a KG intent is set), writes one
    curated markdown file per note under ``docs_dir/<folder>/<slug>.md`` (NOT inserted
    as Findings), then resets the debounce counter + records the taxonomy in state.
    Returns ``{"doc_count", "folders"}``. Best-effort: any failure logs + returns
    ``{"doc_count": 0}``."""
    try:
        store = get_store(ctx.access_token, org_id=ctx.org_id)
        listed = store.list_findings(ctx.kb_id, category="note")
        findings = listed.get("findings", []) if isinstance(listed, dict) else []
        notes = [
            {"title": f.get("title", ""), "content": f.get("content", "")}
            for f in findings
        ]

        schema = _schema_folders(store, ctx.kb_id)
        topics = await _infer_topics(notes)
        for note, topic in zip(notes, topics):
            note["topic"] = topic

        cfg = get_config().living_docs
        layout = plan_layout(
            notes, cluster_min_notes=cfg.cluster_min_notes, schema=schema
        )

        paths = DocPaths(project_path=project_path, kb=kb)
        ensure_layout(paths)
        taxonomy: dict[str, list[str]] = {}
        doc_count = 0
        for entry in layout:
            folder = entry["folder"]
            title = entry["title"]
            content = entry["note"].get("content", "")
            slug = _slug(title) or f"note-{doc_count}"
            target_dir = paths.docs_dir / folder if folder else paths.docs_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / f"{slug}.md").write_text(_render(title, content))
            taxonomy.setdefault(folder, []).append(slug)
            doc_count += 1

        st = load_state(paths)
        st.notes_since_distill = 0
        st.last_distill_at = datetime.now(timezone.utc).isoformat()
        st.taxonomy = taxonomy
        save_state(paths, st)

        folders = sorted(taxonomy.keys())
        logger.info(
            "living-docs distill: %s docs across %s folders (kb=%s)",
            doc_count, len(folders), kb,
        )
        return {"doc_count": doc_count, "folders": folders}
    except Exception:  # noqa: BLE001 — best-effort: must never break a session
        logger.exception("living-docs distill failed for kb=%s", kb)
        return {"doc_count": 0}


# --- scheduling (debounced, fire-and-forget, best-effort) --------------------

_BG_TASKS: set[asyncio.Task] = set()


def schedule_distill(ctx: TenantContext, *, project_path: str, kb: str) -> None:
    """Bump the pending-note counter and, if the debounce trips, fire a distill.

    No-op when ``BRAIN2_LIVING_DOCS=0``. Mirrors ``activity.schedule_activity_update``:
    holds a strong task ref in ``_BG_TASKS`` so it isn't GC'd mid-flight. Best-effort —
    no running event loop (or any error) silently no-ops."""
    if os.getenv("BRAIN2_LIVING_DOCS", "1") == "0":
        return
    try:
        cfg = get_config().living_docs
        paths = DocPaths(project_path=project_path, kb=kb)
        st = load_state(paths)
        st.notes_since_distill += 1
        save_state(paths, st)
        if not should_distill(
            st,
            debounce_n=cfg.distill_debounce_n,
            debounce_minutes=cfg.distill_debounce_minutes,
        ):
            return
        task = asyncio.create_task(run_distill(ctx, project_path=project_path, kb=kb))
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
    except Exception:  # noqa: BLE001 — scheduling is best-effort (e.g. no event loop)
        logger.debug("living-docs distill schedule skipped", exc_info=True)
