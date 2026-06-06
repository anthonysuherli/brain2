"""Embedding client (adapted from Delapan)."""

from __future__ import annotations

import asyncio
from typing import Sequence

from openai import AsyncOpenAI

from br8n.config import get_config, get_settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError(
                "embeddings require OPENAI_API_KEY (needed in both the local and "
                "cloud tiers); set it in the environment or .env"
            )
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed_text(text: str) -> list[float]:
    emb = get_config().embedding
    client = _get_client()
    resp = await client.embeddings.create(
        model=emb.model,
        input=text[: emb.input_char_cap],
    )
    return resp.data[0].embedding


async def embed_batch(texts: Sequence[str]) -> list[list[float]]:
    if not texts:
        return []
    emb = get_config().embedding
    client = _get_client()
    resp = await client.embeddings.create(
        model=emb.model,
        input=[t[: emb.input_char_cap] for t in texts],
    )
    return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]


async def embed_with_retry(text: str, retries: int = 2) -> list[float]:
    for attempt in range(retries + 1):
        try:
            return await embed_text(text)
        except Exception:
            if attempt == retries:
                raise
            await asyncio.sleep(0.4 * (attempt + 1))
    raise RuntimeError("unreachable")
