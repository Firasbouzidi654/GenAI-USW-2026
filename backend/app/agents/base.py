"""Shared LLM factory and helpers for all agents (LangChain 1.x / LangGraph)."""

from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings

# Gleiches Modell wie im ursprünglichen Code — damit der vorhandene API-Key-Zugang passt.
_MODEL = "gemini-3.1-flash-lite-preview"


def get_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=_MODEL,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
    )


def _content_to_text(content) -> str:
    """Wandelt einen Message-Content in Text um.

    Gemini liefert ``AIMessage.content`` oft als Liste von Parts
    (z.B. ``[{"type": "text", "text": "..."}]``) statt als String — beide Formen
    werden hier behandelt.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "".join(parts).strip()
    return ""


def extract_text_output(agent_result: dict) -> str:
    """Extrahiert die finale Textantwort aus dem LangGraph-Agenten-Ergebnis.

    Berücksichtigt nur ``AIMessage``-Objekte (keine Tool-Ausgaben) und nimmt die
    letzte mit echtem Textinhalt.
    """
    messages = agent_result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            text = _content_to_text(msg.content)
            if text:
                return text
    return ""
