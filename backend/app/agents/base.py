"""Shared LLM factory and helpers for all agents (LangChain 1.x / LangGraph)."""

import logging
from typing import Awaitable, Callable, TypeVar

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Substrings that identify a non-retryable auth/key problem. Retrying with a
# different model won't help here since the same API key is rejected outright.
_AUTH_ERROR_MARKERS = ("API_KEY_INVALID", "API key expired", "PERMISSION_DENIED", "UNAUTHENTICATED")


def get_llm(model: str | None = None, temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model or settings.gemini_model_list[0],
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
    )


class AllGeminiModelsFailedError(RuntimeError):
    """Raised when every model in the configured fallback chain failed."""


def _is_auth_error(exc: Exception) -> bool:
    text = str(exc)
    return any(marker in text for marker in _AUTH_ERROR_MARKERS)


async def run_with_model_fallback(
    call: Callable[[ChatGoogleGenerativeAI], Awaitable[T]],
    temperature: float = 0.0,
) -> T:
    """Runs `call` against each model in `settings.gemini_model_list`, in order.

    On any error, falls back to the next model — this covers quota limits
    (429 RESOURCE_EXHAUSTED), availability issues (503), and timeouts, since
    none of those are specific enough to whitelist individually. Auth errors
    (invalid/expired key) abort immediately since switching models with the
    same key would just fail the same way.
    """
    last_exc: Exception | None = None

    for model_name in settings.gemini_model_list:
        try:
            result = await call(get_llm(model=model_name, temperature=temperature))
            logger.info("Gemini call succeeded using model '%s'.", model_name)
            return result
        except Exception as exc:
            if _is_auth_error(exc):
                logger.error(
                    "Gemini auth error with model '%s' - aborting fallback chain: %s",
                    model_name, exc,
                )
                raise
            logger.warning("Gemini model '%s' failed, trying next model: %s", model_name, exc)
            last_exc = exc

    raise AllGeminiModelsFailedError(
        f"All configured Gemini models failed: {settings.gemini_model_list}"
    ) from last_exc


def extract_text_output(agent_result: dict) -> str:
    """Extrahiert die letzte Textantwort aus dem LangGraph-Agenten-Ergebnis."""
    messages = agent_result.get("messages", [])
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if content and isinstance(content, str):
            return content
    return ""
