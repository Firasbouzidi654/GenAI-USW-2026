import logging

import pytest

from app.agents import base


@pytest.mark.asyncio
async def test_groq_fallback_is_used_after_gemini_quota_failure(monkeypatch, caplog):
    monkeypatch.setattr(base.settings, "gemini_models", "gemini-a,gemini-b")
    monkeypatch.setattr(base.settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(base.settings, "groq_model", "llama-3.1-8b-instant")
    monkeypatch.setattr(base, "get_llm", lambda model=None, temperature=0.0: f"gemini:{model}")
    monkeypatch.setattr(base, "get_groq_llm", lambda temperature=0.0: "groq")

    calls = []

    async def invoke(llm):
        calls.append(llm)
        if llm == "groq":
            return "groq answer"
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    with caplog.at_level(logging.WARNING):
        result = await base.run_with_model_fallback(invoke, temperature=0.2)

    assert result == "groq answer"
    assert calls == ["gemini:gemini-a", "groq"]
    assert "Gemini failed, using Groq fallback" in caplog.text


@pytest.mark.asyncio
async def test_missing_groq_keeps_gemini_only_chain(monkeypatch):
    monkeypatch.setattr(base.settings, "gemini_models", "gemini-a,gemini-b")
    monkeypatch.setattr(base.settings, "groq_api_key", "")
    monkeypatch.setattr(base, "get_llm", lambda model=None, temperature=0.0: f"gemini:{model}")

    calls = []

    async def invoke(_llm):
        calls.append(_llm)
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    with pytest.raises(base.AllGeminiModelsFailedError):
        await base.run_with_model_fallback(invoke)

    assert calls == ["gemini:gemini-a", "gemini:gemini-b"]
