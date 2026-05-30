"""Tests für die RAG-Pipeline (Chunking, PDF-Verarbeitung, ChromaDB-Upsert)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag import pipeline
from app.rag.pipeline import _chunk_text, _doc_id, process_document


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_chunk_text_empty_returns_empty_list():
    assert _chunk_text("") == []


def test_chunk_text_short_text_single_chunk():
    chunks = _chunk_text("Kurzer Text.")
    assert len(chunks) == 1
    assert chunks[0] == "Kurzer Text."


def test_chunk_text_long_text_produces_multiple_chunks():
    # Klar über chunk_size (1000) hinaus, damit gesplittet werden muss.
    text = "Absatz eins. " * 200 + "\n\n" + "Absatz zwei. " * 200
    chunks = _chunk_text(text)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)


def test_chunk_text_chunks_respect_max_size():
    text = "x " * 5000
    chunks = _chunk_text(text)
    # Splitter darf leicht überschreiten, aber nicht exzessiv.
    assert all(len(c) <= 1500 for c in chunks)


def test_doc_id_is_stable_for_same_input():
    a = _doc_id("file.pdf", 0, "hallo welt")
    b = _doc_id("file.pdf", 0, "hallo welt")
    assert a == b


def test_doc_id_changes_with_content():
    a = _doc_id("file.pdf", 0, "hallo welt")
    b = _doc_id("file.pdf", 0, "anderer text")
    assert a != b


def test_doc_id_includes_filename_and_index():
    doc_id = _doc_id("vorlesung.pdf", 3, "content")
    assert doc_id.startswith("vorlesung.pdf::3::")


# ---------------------------------------------------------------------------
# process_document
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_document_missing_file_does_nothing():
    # Darf nicht crashen und auch keine Collection-Calls auslösen.
    with patch.object(pipeline, "get_collection") as mock_get:
        await process_document("nicht/vorhanden.pdf")
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_process_document_indexes_chunks(tmp_path):
    pdf_path = tmp_path / "skript.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 dummy")

    fake_collection = MagicMock()

    with patch.object(pipeline, "_extract_text", return_value="Lorem ipsum dolor sit amet. " * 200), \
         patch.object(pipeline, "embed_texts", return_value=[[0.1, 0.2], [0.3, 0.4]]) as mock_embed, \
         patch.object(pipeline, "_chunk_text", return_value=["chunk a", "chunk b"]), \
         patch.object(pipeline, "get_collection", return_value=fake_collection):
        await process_document(str(pdf_path))

    mock_embed.assert_called_once_with(["chunk a", "chunk b"])
    fake_collection.upsert.assert_called_once()
    kwargs = fake_collection.upsert.call_args.kwargs
    assert kwargs["documents"] == ["chunk a", "chunk b"]
    assert kwargs["embeddings"] == [[0.1, 0.2], [0.3, 0.4]]
    assert len(kwargs["ids"]) == 2
    assert all(i.startswith("skript.pdf::") for i in kwargs["ids"])
    assert kwargs["metadatas"] == [
        {"source": "skript.pdf", "chunk": 0},
        {"source": "skript.pdf", "chunk": 1},
    ]


@pytest.mark.asyncio
async def test_process_document_skips_when_no_text(tmp_path):
    pdf_path = tmp_path / "leer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    with patch.object(pipeline, "_extract_text", return_value=""), \
         patch.object(pipeline, "get_collection") as mock_get:
        await process_document(str(pdf_path))
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_process_document_skips_when_embeddings_fail(tmp_path):
    pdf_path = tmp_path / "skript.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_collection = MagicMock()

    with patch.object(pipeline, "_extract_text", return_value="ein bisschen text"), \
         patch.object(pipeline, "_chunk_text", return_value=["chunk a"]), \
         patch.object(pipeline, "embed_texts", return_value=[]), \
         patch.object(pipeline, "get_collection", return_value=fake_collection):
        await process_document(str(pdf_path))
    fake_collection.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_process_document_skips_when_chroma_unavailable(tmp_path):
    pdf_path = tmp_path / "skript.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    with patch.object(pipeline, "_extract_text", return_value="text"), \
         patch.object(pipeline, "_chunk_text", return_value=["a"]), \
         patch.object(pipeline, "embed_texts", return_value=[[0.1]]), \
         patch.object(pipeline, "get_collection", return_value=None):
        # Darf nicht crashen.
        await process_document(str(pdf_path))


@pytest.mark.asyncio
async def test_process_document_swallows_upsert_errors(tmp_path):
    pdf_path = tmp_path / "skript.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_collection = MagicMock()
    fake_collection.upsert.side_effect = RuntimeError("chroma kaputt")

    with patch.object(pipeline, "_extract_text", return_value="text"), \
         patch.object(pipeline, "_chunk_text", return_value=["a"]), \
         patch.object(pipeline, "embed_texts", return_value=[[0.1]]), \
         patch.object(pipeline, "get_collection", return_value=fake_collection):
        # Upload soll auch dann nicht 500 werden, wenn Chroma-Upsert wirft.
        await process_document(str(pdf_path))
