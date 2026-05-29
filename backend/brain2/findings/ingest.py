"""Shared text → findings ingest: chunk → embed → persist.

    text ──► chunk_text ──► embed_batch ──► findings rows (user client, RLS)

Lifted out of `tools/ingest.py` so both the file-upload tool and the MCP
`divergence_ingest_text` path share one chunk/embed/persist implementation.
Writes go through the **user-scoped** client so RLS stays authoritative
(matches CLAUDE.md's ingest convention).
"""

from __future__ import annotations

from brain2.agent.state import TenantContext
from brain2.agent.synopsis import schedule_rebuild
from brain2.clients.embeddings import embed_batch
from brain2.config import get_config
from brain2.store import get_store


def chunk_text(text: str, max_chars: int | None = None) -> list[str]:
    """Naive paragraph-aware chunker. Good enough for v0; swap for Unstructured later."""
    if max_chars is None:
        max_chars = get_config().embedding.chunk_max_chars
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    n = 0
    for p in paragraphs:
        if n + len(p) > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf, n = [], 0
        buf.append(p)
        n += len(p)
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def _title_from_chunk(chunk: str) -> str:
    first_line = chunk.strip().split("\n", 1)[0]
    return first_line[:96] if first_line else "Untitled chunk"


async def persist_chunks(
    ctx: TenantContext,
    chunks: list[str],
    *,
    source: str,
    category: str = "document",
    tags: list[str] | None = None,
    title: str | None = None,
) -> list[str]:
    """Embed + insert chunks as findings; return the new ids.

    `title` overrides the derived title only when there is a single chunk;
    multi-chunk ingests always derive a per-chunk title from the first line."""
    if not chunks:
        return []
    embeddings = await embed_batch(chunks)
    single = len(chunks) == 1
    rows = [
        {
            "org_id": ctx.org_id,
            "kb_id": ctx.kb_id,
            "title": (title if (single and title) else _title_from_chunk(c)),
            "content": c,
            "category": category,
            "confidence": 1.0,
            "tags": tags if tags is not None else ["upload"],
            "provenance": [{"source": source}],
            "embedding": emb,
        }
        for c, emb in zip(chunks, embeddings)
    ]
    return await get_store(ctx.access_token).insert_findings(rows)


async def ingest_text(
    ctx: TenantContext,
    text: str,
    *,
    title: str | None = None,
    category: str = "document",
    tags: list[str] | None = None,
    source: str = "text",
) -> dict:
    """Chunk, embed, and persist raw text as findings. Fires a synopsis rebuild
    when anything was written (mirrors explore/file-ingest)."""
    chunks = chunk_text(text)
    finding_ids = await persist_chunks(
        ctx, chunks, source=source, category=category, tags=tags or ["text"], title=title
    )
    if finding_ids:
        schedule_rebuild(ctx)
    return {"finding_count": len(finding_ids), "finding_ids": finding_ids}
