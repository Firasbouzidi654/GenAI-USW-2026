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


def _build_where(
    source_filter: list[str] | None,
    chat_id: str | None,
    user_id: str | None,
    metadata_filter: dict | None = None,
) -> dict | None:
    """Baut den ChromaDB-``where``-Filter.

    Mehrere Bedingungen werden mit ``$and`` kombiniert (ChromaDB-Anforderung).
    ``chat_id``/``user_id`` sorgen für die Isolation zwischen Chats und Nutzern.
    """
    conditions: list[dict] = []
    if source_filter:
        if len(source_filter) == 1:
            conditions.append({"source": {"$eq": source_filter[0]}})
        else:
            conditions.append({"source": {"$in": source_filter}})
    if chat_id is not None:
        conditions.append({"chat_id": {"$eq": chat_id}})
    if user_id is not None:
        conditions.append({"user_id": {"$eq": user_id}})
    for key, value in (metadata_filter or {}).items():
        if value is None:
            continue
        conditions.append({key: {"$eq": value}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def has_indexed_source(
    source: str,
    user_id: str | None = None,
    metadata_filter: dict | None = None,
) -> bool:
    """Checks whether Chroma already contains chunks for a source and metadata scope."""
    if not source:
        return False
    collection = get_collection()
    if collection is None:
        return False
    where = _build_where([source], None, user_id, metadata_filter)
    try:
        result = collection.get(where=where, limit=1)
    except Exception as exc:
        logger.warning("Chroma-Existenzcheck fehlgeschlagen: %s", exc)
        return False
    return bool(result.get("ids"))


async def retrieve_context(
    query: str,
    source_filter: list[str] | None = None,
    n_results: int | None = None,
    threshold: float | None = 0.4,
    chat_id: str | None = None,
    user_id: str | None = None,
    metadata_filter: dict | None = None,
) -> str:
    """Sucht in ChromaDB die für ``query`` relevantesten Chunks und gibt sie als Text zurück.

    Schritte:
      1. Query embedden (Gemini)
      2. Top-K Chunks in ChromaDB suchen (gefiltert nach Dokumentnamen + chat_id/user_id)
      3. Treffer zu einem einzigen Kontext-String zusammenfügen

    Args:
        query: Die Suchanfrage.
        source_filter: Optionale Liste von Dateinamen (``source``-Metadatenfeld).
        n_results: Anzahl zurückgegebener Chunks. Überschreibt ``settings.rag_top_k``.
        threshold: Cosine-Distance-Schwellenwert (0–2). ``None`` deaktiviert die Filterung.
        chat_id: Beschränkt die Suche auf Dokumente dieses Chats (Isolation).
        user_id: Beschränkt die Suche auf Dokumente dieses Nutzers (Multi-User).
        metadata_filter: Zusätzliche Chroma-Metadatenfilter, z.B. Moodle-Kurs-ID.

    Bei jedem Fehler (kein Chroma, kein Embedding, kein Treffer) wird ein
    leerer String zurückgegeben.
    """
    if not query or not query.strip():
        return ""

    collection = get_collection()
    if collection is None:
        return ""

    embeddings = embed_texts([query])
    if not embeddings:
        return ""

    where = _build_where(source_filter, chat_id, user_id, metadata_filter)

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

    # threshold=None means no distance filtering (used by quiz to retrieve all
    # content from specified docs regardless of query relevance).
    # threshold=0.4 (default) keeps only genuinely relevant chunks for chat Q&A.
    if threshold is not None and distances:
        filtered = [
            (d, m)
            for d, m, dist in zip(documents, metadatas, distances)
            if dist < threshold
        ]
        if not filtered:
            return ""
        documents, metadatas = zip(*filtered)

    return _format_context(list(documents), list(metadatas))
