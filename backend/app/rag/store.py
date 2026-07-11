"""Gemeinsame Bausteine für die RAG-Pipeline.

Stellt einen lazy-initialisierten ChromaDB-Client, eine Collection sowie
Hilfsfunktionen zum Embedden von Texten über Gemini bereit. Alle Funktionen
sind so geschrieben, dass sie bei fehlender Infrastruktur (kein Chroma,
kein Netz, ungültiger Key) nicht hart abbrechen – das schützt API-Routen
und Tests, die ohne laufende Dienste auskommen müssen.
"""

from __future__ import annotations

import logging
from typing import Iterable

from google import genai

from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy-Singletons – erst beim ersten Zugriff aufbauen, damit Import-Zeit
# nicht von ChromaDB / Netzwerk abhängt.
_chroma_client = None
_collection = None
_genai_client: genai.Client | None = None


def get_genai_client() -> genai.Client:
    """Gibt einen wiederverwendbaren google-genai Client zurück."""
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=settings.gemini_api_key)
    return _genai_client


def get_collection():
    """Liefert die Chroma-Collection oder ``None``, falls Chroma nicht erreichbar ist."""
    global _chroma_client, _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb

        _chroma_client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        _collection = _chroma_client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        return _collection
    except Exception as exc:  # pragma: no cover - defensiv
        logger.warning("ChromaDB nicht erreichbar: %s", exc)
        return None


_local_embedder = None


def _get_local_embedder():
    """Lädt (lazy) das lokale fastembed-Modell; wirft, wenn nicht verfügbar."""
    global _local_embedder
    if _local_embedder is None:
        from fastembed import TextEmbedding
        _local_embedder = TextEmbedding(model_name=settings.local_embedding_model)
    return _local_embedder


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    """Erzeugt Embeddings für eine Liste von Texten.

    Standard: lokale Embeddings (fastembed) — kein API-Ratenlimit, offline. Bei Fehler
    (oder ``use_local_embeddings=False``) Fallback auf Gemini. Gibt bei Fehlern eine
    leere Liste zurück, damit Aufrufer defensiv weiterarbeiten können.
    """
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return []

    if settings.use_local_embeddings:
        try:
            embedder = _get_local_embedder()
            return [[float(x) for x in vec] for vec in embedder.embed(list(texts))]
        except Exception as exc:
            logger.warning("Lokale Embeddings fehlgeschlagen (%s) — Fallback auf Gemini.", exc)

    try:
        client = get_genai_client()
        result = client.models.embed_content(
            model=settings.embedding_model,
            contents=texts,
        )
        embeddings = getattr(result, "embeddings", None) or []
        return [list(e.values) for e in embeddings]
    except Exception as exc:
        logger.warning("Embedding fehlgeschlagen: %s", exc)
        return []


def clear_collection() -> bool:
    """Löscht ALLE Chunks aus der Collection. Gibt True bei Erfolg zurück."""
    global _chroma_client, _collection
    try:
        client = _chroma_client
        if client is None:
            get_collection()
            client = _chroma_client
        if client is None:
            return False
        client.delete_collection(name=settings.chroma_collection)
        _collection = None  # beim nächsten Zugriff neu (leer) anlegen
        return True
    except Exception as exc:
        logger.warning("ChromaDB-Collection konnte nicht geleert werden: %s", exc)
        return False


def reset_state() -> None:
    """Nur für Tests: Singletons zurücksetzen."""
    global _chroma_client, _collection, _genai_client
    _chroma_client = None
    _collection = None
    _genai_client = None
