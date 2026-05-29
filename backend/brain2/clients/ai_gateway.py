"""Vercel AI Gateway client — Phase 3 exploration pipeline (adapted from Divergence)."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import TypeVar

from openai import AsyncOpenAI, omit
from pydantic import BaseModel

from brain2.config import get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=1)
def gateway_client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(api_key=s.ai_gateway_api_key, base_url=s.ai_gateway_base_url)


async def structured_completion(
    *,
    model: str,
    response_format: type[T],
    system: str,
    user: str,
    temperature: float = 0.0,
    fallback_model: str | None = None,
    use_json_schema: bool = True,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
) -> T:
    models = [model]
    if fallback_model and fallback_model != model:
        models.append(fallback_model)
    last_exc: Exception | None = None
    for m in models:
        try:
            return await _attempt(m, response_format, system, user, temperature, use_json_schema, max_tokens, reasoning_effort)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("structured_completion failed on model=%s: %s", m, exc)
    assert last_exc is not None
    raise last_exc


async def _attempt(model, response_format, system, user, temperature, use_json_schema, max_tokens, reasoning_effort):
    if not use_json_schema:
        return await _parse_prompt_json(model, response_format, system, user, temperature, max_tokens, reasoning_effort)
    try:
        return await _parse_json_schema(model, response_format, system, user, temperature, max_tokens, reasoning_effort)
    except Exception as exc:  # noqa: BLE001
        logger.info("json_schema failed for %s (%s); retrying prompt-JSON", model, exc)
        return await _parse_prompt_json(model, response_format, system, user, temperature, max_tokens, reasoning_effort)


async def _parse_json_schema(model, response_format, system, user, temperature, max_tokens, reasoning_effort):
    completion = await gateway_client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": response_format.__name__, "schema": response_format.model_json_schema()}},
        temperature=temperature,
        max_tokens=max_tokens if max_tokens is not None else omit,
        reasoning_effort=reasoning_effort if reasoning_effort is not None else omit,
    )
    return response_format.model_validate_json(completion.choices[0].message.content or "")


async def _parse_prompt_json(model, response_format, system, user, temperature, max_tokens, reasoning_effort):
    schema = json.dumps(response_format.model_json_schema())
    completion = await gateway_client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": f"{system}\n\nReturn ONLY a single JSON object matching this JSON Schema. No prose:\n{schema}"}, {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens if max_tokens is not None else omit,
        reasoning_effort=reasoning_effort if reasoning_effort is not None else omit,
    )
    content = completion.choices[0].message.content or ""
    return response_format.model_validate_json(_strip_fences(content))


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
