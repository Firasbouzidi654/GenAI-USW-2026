"""Small helpers for transparent chat answer source labels."""

SOURCE_SEPARATOR = "──────────────────"
MOODLE_API_SOURCE = "Quelle: Moodle API (Live-Daten)"
MOODLE_RAG_SOURCE = "Quelle: Moodle RAG (ChromaDB + Gemini)"


def append_source(answer: str, source: str) -> str:
    """Append a visually separated source label without changing answer content."""
    text = (answer or "").rstrip()
    if not text:
        return source
    if source in text:
        return text
    return f"{text}\n\n{SOURCE_SEPARATOR}\n{source}"
