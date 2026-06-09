"""RAG-Retriever: nimmt eine User-Frage und liefert relevanten Kontext."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.rag.store import embed_texts, get_collection

logger = logging.getLogger(__name__)


def _format_context(documents: list[str], metadatas: list[dict]) -> str:
    """Formatiert die Treffer als sauberen Kontextblock für das LLM."""
    parts: list[str] = []
    for idx, doc in enumerate(documents, start=1):
        source = ""
        if idx - 1 < len(metadatas) and isinstance(metadatas[idx - 1], dict):
            source = metadatas[idx - 1].get("source", "")
        header = f"[Quelle {idx}{f' – {source}' if source else ''}]"
        parts.append(f"{header}\n{doc.strip()}")
    return "\n\n".join(parts)


async def retrieve_context(
    query: str,
    source_filter: list[str] | None = None,
    n_results: int | None = None,
) -> str:
    """Sucht in ChromaDB die für ``query`` relevantesten Chunks und gibt sie als Text zurück.

    Schritte:
      1. Query embedden (Gemini)
      2. Top-K Chunks in ChromaDB suchen (optional gefiltert nach Dokumentnamen)
      3. Treffer zu einem einzigen Kontext-String zusammenfügen

    Args:
        query: Die Suchanfrage.
        source_filter: Optionale Liste von Dateinamen (``source``-Metadatenfeld).
            Bei einer Datei wird ``$eq``, bei mehreren ``$in`` verwendet.
            Ohne Angabe wird über alle Dokumente gesucht.
        n_results: Anzahl zurückgegebener Chunks. Überschreibt ``settings.rag_top_k``.
            Nützlich für Quiz-Generierung, die breiteren Dokumentkontext benötigt.

    Bei jedem Fehler (kein Chroma, kein Embedding, kein Treffer) wird ein
    leerer String zurückgegeben – die Prompt-Route fällt dann sauber auf
    eine reine LLM-Antwort ohne RAG-Kontext zurück.
    """
    if not query or not query.strip():
        return ""

    collection = get_collection()
    if collection is None:
        return ""

    embeddings = embed_texts([query])
    if not embeddings:
        return ""

    where: dict | None = None
    if source_filter:
        if len(source_filter) == 1:
            where = {"source": {"$eq": source_filter[0]}}
        else:
            where = {"source": {"$in": source_filter}}

    try:
        query_kwargs: dict = {
            "query_embeddings": embeddings,
            "n_results": n_results if n_results is not None else settings.rag_top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            query_kwargs["where"] = where
        result = collection.query(**query_kwargs)
    except Exception as exc:
        logger.warning("Chroma-Query fehlgeschlagen: %s", exc)
        return ""

    documents_batches = result.get("documents") or []
    metadatas_batches = result.get("metadatas") or []
    distances_batches = result.get("distances") or []
    if not documents_batches or not documents_batches[0]:
        return ""

    documents = documents_batches[0]
    metadatas = metadatas_batches[0] if metadatas_batches else []
    distances = distances_batches[0] if distances_batches else []

    # Cosine distance: 0 = identical, ~0.46 = unrelated in practice.
    # Only include chunks that are actually relevant to the query.
    threshold = 0.4
    if distances:
        filtered = [(d, m) for d, m, dist in zip(documents, metadatas, distances) if dist < threshold]
        if not filtered:
            return ""
        documents, metadatas = zip(*filtered)

    return _format_context(list(documents), list(metadatas))
