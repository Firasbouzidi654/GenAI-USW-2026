"""RAG-Pipeline: PDF -> Text -> Chunks -> Embeddings -> ChromaDB."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from app.core.config import settings
from app.rag.store import embed_texts, get_collection

logger = logging.getLogger(__name__)


def _extract_text(pdf_path: Path) -> str:
    """Extrahiert reinen Text aus einer PDF-Datei."""
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        logger.warning("pypdf ist nicht installiert; PDF kann nicht gelesen werden.")
        return ""

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        logger.warning("PDF konnte nicht geöffnet werden (%s): %s", pdf_path, exc)
        return ""

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(pages).strip()


def _chunk_text(text: str) -> list[str]:
    """Teilt den Text in überlappende Chunks."""
    if not text:
        return []
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        return [c for c in splitter.split_text(text) if c.strip()]
    except ImportError:
        # Fallback: simples Sliding-Window-Chunking
        size = settings.rag_chunk_size
        overlap = settings.rag_chunk_overlap
        step = max(1, size - overlap)
        return [text[i : i + size] for i in range(0, len(text), step) if text[i : i + size].strip()]


def _doc_id(filename: str, chunk_index: int, content: str) -> str:
    digest = hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"{filename}::{chunk_index}::{digest}"


def process_document_sync(file_path: str) -> None:
    """Synchronous pipeline — called by BackgroundTasks (runs in a thread pool).

    Steps: extract text → chunk → embed via Gemini → upsert into ChromaDB.
    Never raises; failures are logged so the upload response is never blocked.
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        logger.warning("PDF nicht gefunden: %s", file_path)
        return

    text = _extract_text(path)
    if not text:
        logger.info("Kein Text extrahierbar aus %s", file_path)
        return

    chunks = _chunk_text(text)
    if not chunks:
        return

    embeddings = embed_texts(chunks)
    if not embeddings or len(embeddings) != len(chunks):
        logger.warning(
            "Embeddings konnten nicht erzeugt werden (%d Chunks, %d Embeddings)",
            len(chunks),
            len(embeddings),
        )
        return

    collection = get_collection()
    if collection is None:
        logger.warning("ChromaDB nicht verfügbar — Dokument nicht indexiert.")
        return

    filename = path.name
    ids = [_doc_id(filename, i, chunk) for i, chunk in enumerate(chunks)]
    metadatas = [{"source": filename, "chunk": i} for i in range(len(chunks))]

    try:
        collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("Indexiert: %s (%d Chunks)", filename, len(chunks))
    except Exception as exc:
        logger.warning("Speichern in ChromaDB fehlgeschlagen: %s", exc)


async def process_document(file_path: str) -> None:
    """Async wrapper kept for backwards compatibility."""
    import asyncio
    await asyncio.to_thread(process_document_sync, file_path)
