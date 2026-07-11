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


def relevant_sources_for_query(
    query: str,
    metadata_filter: dict | None = None,
    user_id: str | None = None,
    n_results: int = 30,
    max_files: int = 6,
    margin: float = 0.15,
) -> list[str]:
    """Liefert die zum ``query`` thematisch relevanten Quell-Dokumente (Dateinamen).

    Nutzt Vektor-Ähnlichkeit: eine Quelle gilt als relevant, wenn ihr bester Chunk
    nah genug am besten Gesamttreffer liegt (``best + margin``). So wird z.B. für
    „Virtualisierung" nur das Virtualisierungs-/Docker-Material gewählt statt des
    ganzen Kurses. Rückgabe in Relevanz-Reihenfolge, max. ``max_files`` Dateien.
    """
    if not query or not query.strip():
        return []
    collection = get_collection()
    if collection is None:
        return []
    embeddings = embed_texts([query])
    if not embeddings:
        return []
    where = _build_where(None, None, user_id, metadata_filter)
    kwargs: dict = {"query_embeddings": embeddings, "n_results": n_results,
                    "include": ["metadatas", "distances"]}
    if where is not None:
        kwargs["where"] = where
    try:
        result = collection.query(**kwargs)
    except Exception as exc:
        logger.warning("Relevanz-Quellensuche fehlgeschlagen: %s", exc)
        return []

    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    best_per_source: dict[str, float] = {}
    order: list[str] = []
    for meta, dist in zip(metas, dists):
        if not isinstance(meta, dict):
            continue
        src = meta.get("source")
        if not src or dist is None:
            continue
        if src not in best_per_source:
            best_per_source[src] = dist
            order.append(src)
        elif dist < best_per_source[src]:
            best_per_source[src] = dist
    if not order:
        return []
    best = min(best_per_source.values())
    cutoff = best + margin
    selected = [s for s in order if best_per_source[s] <= cutoff]
    return (selected or order[:1])[:max_files]


def count_indexed_chunks(
    source_documents: list[str] | None = None,
    metadata_filter: dict | None = None,
    user_id: str | None = None,
) -> int:
    """Zählt die indexierten Chunks für die angegebenen Quellen (Maß für den Stoffumfang)."""
    collection = get_collection()
    if collection is None:
        return 0
    where = _build_where(source_documents, None, user_id, metadata_filter)
    try:
        result = collection.get(where=where, include=[])
    except Exception as exc:
        logger.warning("Chunk-Zählung fehlgeschlagen: %s", exc)
        return 0
    return len(result.get("ids") or [])


def has_indexed_course(course_id, user_id: str | None = None) -> bool:
    """Prüft, ob für einen Moodle-Kurs (course_id-Metadaten) bereits Chunks existieren."""
    if course_id is None:
        return False
    collection = get_collection()
    if collection is None:
        return False
    where = _build_where(None, None, user_id, {"course_id": course_id})
    try:
        result = collection.get(where=where, limit=1)
    except Exception as exc:
        logger.warning("Chroma-Kurs-Existenzcheck fehlgeschlagen: %s", exc)
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

    # Live-Trace (nur wenn eine Chat-Anfrage läuft) — Observability/Präsentation
    try:
        from app.observability import trace_bus
        if trace_bus.current_trace_id.get():
            scope = "Moodle-Kurs" if (metadata_filter or {}).get("course_id") else (
                ", ".join(source_filter) if source_filter else "alle Dokumente"
            )
            trace_bus.publish("rag", "rag", "RAG-Vektorsuche", f"{query[:80]} · Quelle: {scope}")
    except Exception:
        pass

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

    # Genutzte Quell-Dokumente für die Provenance-Anzeige im Chat vermerken.
    try:
        from app.observability import trace_bus
        if trace_bus.current_provenance.get() is not None:
            for meta in metadatas:
                if not isinstance(meta, dict):
                    continue
                name = meta.get("source") or meta.get("filename")
                if not name:
                    continue
                course = meta.get("course_name")
                kind = "moodle" if (meta.get("moodle") or course) else "upload"
                trace_bus.add_source(str(name), kind, str(course) if course else None)
    except Exception:
        pass

    return _format_context(list(documents), list(metadatas))
