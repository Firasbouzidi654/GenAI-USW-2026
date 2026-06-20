"""Shared LLM factory and helpers for all agents (LangChain 1.x / LangGraph)."""

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings

_MODEL = "gemini-2.0-flash-lite"


def get_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=_MODEL,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
    )


def extract_text_output(agent_result: dict) -> str:
    """Extrahiert die letzte Textantwort aus dem LangGraph-Agenten-Ergebnis."""
    messages = agent_result.get("messages", [])
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if content and isinstance(content, str):
            return content
    return ""
