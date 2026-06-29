"""RAG-Pipeline: PDF -> Text -> Chunks -> Embeddings -> ChromaDB."""

from __future__ import annotations

import hashlib
import logging
import re
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


def _split_pptx_slides(text: str) -> list[str]:
    matches = list(re.finditer(r"(?m)^Slide\s+\d+(?::\s*[^\n]+)?", text or ""))
    if not matches:
        return [text] if text and text.strip() else []
    slides: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        slide_text = text[match.start():end].strip()
        if slide_text:
            slides.append(slide_text)
    return slides


def _chunk_document_text(filename: str, text: str) -> list[str]:
    if filename.lower().endswith(".pptx"):
        chunks: list[str] = []
        for slide_text in _split_pptx_slides(text):
            chunks.extend(_chunk_text(slide_text))
        return chunks
    return _chunk_text(text)


def _doc_id(filename: str, chunk_index: int, content: str, chat_id: str | None) -> str:
    digest = hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()[:8]
    scope = chat_id or "global"
    return f"{scope}::{filename}::{chunk_index}::{digest}"


def _infer_slide_metadata(filename: str, chunk: str) -> dict:
    if not filename.lower().endswith(".pptx"):
        return {}
    match = re.search(r"(?:^|\n)Slide\s+(\d+)(?::\s*([^\n]+))?", chunk, flags=re.IGNORECASE)
    if not match:
        return {}
    meta = {"slide_number": int(match.group(1))}
    if match.group(2):
        meta["slide_title"] = match.group(2).strip()[:160]
    return meta


def process_document_sync(
    file_path: str,
    chat_id: str | None = None,
    user_id: str = "local",
) -> None:
    """Synchronous pipeline — called by BackgroundTasks (runs in a thread pool).

    Steps: extract text → chunk → embed via Gemini → upsert into ChromaDB.
    Jeder Chunk erhält ``chat_id`` und ``user_id`` als Metadaten, damit die
    Dokumente verschiedener Chats/Nutzer in der Vektor-DB getrennt bleiben.
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

    chunks = _chunk_document_text(path.name, text)
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
    ids = [_doc_id(filename, i, chunk, chat_id) for i, chunk in enumerate(chunks)]
    metadatas = [
        {
            "source": filename,
            "chunk": i,
            "chat_id": chat_id or "",
            "user_id": user_id or "local",
        }
        for i in range(len(chunks))
    ]

    try:
        collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("Indexiert: %s (%d Chunks, chat=%s)", filename, len(chunks), chat_id)
    except Exception as exc:
        logger.warning("Speichern in ChromaDB fehlgeschlagen: %s", exc)


async def process_document(
    file_path: str, chat_id: str | None = None, user_id: str = "local"
) -> None:
    """Async wrapper kept for backwards compatibility."""
    import asyncio
    await asyncio.to_thread(process_document_sync, file_path, chat_id, user_id)


def index_text(
    filename: str,
    text: str,
    chat_id: str | None = None,
    user_id: str = "local",
    extra_meta: dict | None = None,
) -> int:
    """Indexiert bereits extrahierten Text in ChromaDB (z.B. aus einem Moodle-Download).

    Returns die Anzahl gespeicherter Chunks (0 bei Fehlern/leerem Text).
    """
    if not text or not text.strip():
        return 0

    chunks = _chunk_document_text(filename, text)
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)
    if not embeddings or len(embeddings) != len(chunks):
        logger.warning("Embeddings für %s konnten nicht erzeugt werden.", filename)
        return 0

    collection = get_collection()
    if collection is None:
        logger.warning("ChromaDB nicht verfügbar — %s nicht indexiert.", filename)
        return 0

    ids = [_doc_id(filename, i, chunk, chat_id) for i, chunk in enumerate(chunks)]
    metadatas = []
    for i in range(len(chunks)):
        meta = {
            "source": filename,
            "chunk": i,
            "chat_id": chat_id or "",
            "user_id": user_id or "local",
        }
        if extra_meta:
            meta.update(extra_meta)
        meta.update(_infer_slide_metadata(filename, chunks[i]))
        metadatas.append(meta)

    try:
        collection.upsert(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
        logger.info("Indexiert (Text): %s (%d Chunks, chat=%s)", filename, len(chunks), chat_id)
        return len(chunks)
    except Exception as exc:
        logger.warning("Speichern in ChromaDB fehlgeschlagen (%s): %s", filename, exc)
        return 0
