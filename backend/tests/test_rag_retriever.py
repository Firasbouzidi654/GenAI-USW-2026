"""Tests für den RAG-Retriever."""

from unittest.mock import MagicMock, patch

import pytest

from app.rag import retriever
from app.rag.retriever import _format_context, has_indexed_source, retrieve_context


# ---------------------------------------------------------------------------
# _format_context
# ---------------------------------------------------------------------------


def test_format_context_includes_source_header():
    out = _format_context(
        ["Erster Chunk."],
        [{"source": "skript.pdf", "chunk": 0}],
    )
    assert "[Quelle 1 – skript.pdf]" in out
    assert "Erster Chunk." in out


def test_format_context_handles_missing_metadata():
    out = _format_context(["nur text"], [])
    assert "[Quelle 1]" in out
    assert "nur text" in out


def test_format_context_joins_multiple_chunks():
    out = _format_context(
        ["A", "B"],
        [{"source": "x.pdf"}, {"source": "y.pdf"}],
    )
    assert "Quelle 1" in out and "Quelle 2" in out
    assert out.index("A") < out.index("B")


# ---------------------------------------------------------------------------
# retrieve_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_context_empty_query_returns_empty_string():
    result = await retrieve_context("")
    assert result == ""


@pytest.mark.asyncio
async def test_retrieve_context_no_collection_returns_empty_string():
    with patch.object(retriever, "get_collection", return_value=None):
        result = await retrieve_context("Was ist SQL?")
    assert result == ""


@pytest.mark.asyncio
async def test_retrieve_context_no_embeddings_returns_empty_string():
    fake_collection = MagicMock()
    with patch.object(retriever, "get_collection", return_value=fake_collection), \
         patch.object(retriever, "embed_texts", return_value=[]):
        result = await retrieve_context("Was ist SQL?")
    assert result == ""
    fake_collection.query.assert_not_called()


@pytest.mark.asyncio
async def test_retrieve_context_returns_formatted_hits():
    fake_collection = MagicMock()
    fake_collection.query.return_value = {
        "documents": [["SQL ist eine Abfragesprache.", "Joins kombinieren Tabellen."]],
        "metadatas": [[{"source": "db.pdf"}, {"source": "db.pdf"}]],
    }
    with patch.object(retriever, "get_collection", return_value=fake_collection), \
         patch.object(retriever, "embed_texts", return_value=[[0.1, 0.2]]):
        result = await retrieve_context("Was ist SQL?")

    fake_collection.query.assert_called_once()
    kwargs = fake_collection.query.call_args.kwargs
    assert kwargs["query_embeddings"] == [[0.1, 0.2]]
    assert kwargs["n_results"] >= 1
    assert "SQL ist eine Abfragesprache." in result
    assert "Joins kombinieren Tabellen." in result
    assert "db.pdf" in result


@pytest.mark.asyncio
async def test_retrieve_context_no_hits_returns_empty_string():
    fake_collection = MagicMock()
    fake_collection.query.return_value = {"documents": [[]], "metadatas": [[]]}
    with patch.object(retriever, "get_collection", return_value=fake_collection), \
         patch.object(retriever, "embed_texts", return_value=[[0.1]]):
        result = await retrieve_context("frage")
    assert result == ""


@pytest.mark.asyncio
async def test_retrieve_context_swallows_query_errors():
    fake_collection = MagicMock()
    fake_collection.query.side_effect = RuntimeError("chroma down")
    with patch.object(retriever, "get_collection", return_value=fake_collection), \
         patch.object(retriever, "embed_texts", return_value=[[0.1]]):
        result = await retrieve_context("frage")
    assert result == ""


@pytest.mark.asyncio
async def test_retrieve_context_applies_metadata_filter():
    fake_collection = MagicMock()
    fake_collection.query.return_value = {
        "documents": [["Moodle chunk"]],
        "metadatas": [[{"source": "session1.pdf", "course_id": 58776, "moodle": "1"}]],
    }
    with patch.object(retriever, "get_collection", return_value=fake_collection), \
         patch.object(retriever, "embed_texts", return_value=[[0.1]]):
        result = await retrieve_context(
            "Session 1",
            source_filter=["session1.pdf"],
            metadata_filter={"moodle": "1", "course_id": 58776},
        )

    kwargs = fake_collection.query.call_args.kwargs
    assert kwargs["where"] == {
        "$and": [
            {"source": {"$eq": "session1.pdf"}},
            {"moodle": {"$eq": "1"}},
            {"course_id": {"$eq": 58776}},
        ]
    }
    assert "Moodle chunk" in result


def test_has_indexed_source_checks_metadata_scope():
    fake_collection = MagicMock()
    fake_collection.get.return_value = {"ids": ["chunk-1"]}
    with patch.object(retriever, "get_collection", return_value=fake_collection):
        exists = has_indexed_source(
            "slides.pptx",
            user_id="local",
            metadata_filter={"moodle": "1", "course_id": 58776},
        )

    assert exists is True
    assert fake_collection.get.call_args.kwargs["where"] == {
        "$and": [
            {"source": {"$eq": "slides.pptx"}},
            {"user_id": {"$eq": "local"}},
            {"moodle": {"$eq": "1"}},
            {"course_id": {"$eq": 58776}},
        ]
    }
