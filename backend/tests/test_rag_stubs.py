import pytest

from app.rag.pipeline import process_document
from app.rag.retriever import retrieve_context


@pytest.mark.asyncio
async def test_retrieve_context_returns_string():
    result = await retrieve_context("test query")
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_process_document_completes():
    await process_document("fake/path.pdf")