"""Anthropic client wrapper — used for synopsis rebuild (adapted from Delapan)."""

from __future__ import annotations

from functools import lru_cache

from langchain_anthropic import ChatAnthropic

from brain2.config import get_config, get_settings


@lru_cache(maxsize=2)
def chat_model(model: str | None = None) -> ChatAnthropic:
    settings = get_settings()
    agent = get_config().agent
    kwargs: dict = dict(
        model=model or agent.model,
        anthropic_api_key=settings.anthropic_api_key,
        max_tokens=agent.max_tokens,
        streaming=True,
    )
    if agent.thinking_budget > 0:
        kwargs["temperature"] = 1.0
        kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": min(agent.thinking_budget, agent.max_tokens - 1),
        }
    else:
        kwargs["temperature"] = agent.temperature
    return ChatAnthropic(**kwargs)  # type: ignore[arg-type]
