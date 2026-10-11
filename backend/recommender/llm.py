from __future__ import annotations

from openai import AsyncOpenAI

from recommender.config import settings


def get_client() -> AsyncOpenAI:
    if not settings.has_valid_api_key:
        raise RuntimeError(
            "No usable LLM key. For free Gemini: set GEMINI_API_KEY in .env "
            "(https://aistudio.google.com/apikey). Or set LLM_PROVIDER=ollama."
        )
    kwargs: dict = {
        "api_key": settings.resolved_api_key,
        "timeout": settings.request_timeout_s,
        "max_retries": 0,
    }
    if settings.resolved_base_url:
        kwargs["base_url"] = settings.resolved_base_url
    return AsyncOpenAI(**kwargs)


def chat_kwargs() -> dict:
    """Gemini 3 spends a long time in thinking mode. Keep replies short enough to return."""
    if settings.llm_provider == "gemini":
        return {"reasoning_effort": "low"}
    return {}
