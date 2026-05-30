"""Tests für die geteilten Bausteine (Gemini-Embeddings, ChromaDB-Client)."""

from unittest.mock import MagicMock, patch

import pytest

from app.rag import store


@pytest.fixture(autouse=True)
def _reset_store_singletons():
    """Setzt Lazy-Singletons vor jedem Test zurück."""
    store.reset_state()
    yield
    store.reset_state()


# ---------------------------------------------------------------------------
# embed_texts
# ---------------------------------------------------------------------------


def test_embed_texts_empty_input_returns_empty_list():
    assert store.embed_texts([]) == []
    assert store.embed_texts(["", "   "]) == []


def test_embed_texts_returns_vectors_from_genai():
    fake_client = MagicMock()
    fake_client.models.embed_content.return_value = MagicMock(
        embeddings=[MagicMock(values=[0.1, 0.2]), MagicMock(values=[0.3, 0.4])]
    )
    with patch.object(store, "get_genai_client", return_value=fake_client):
        result = store.embed_texts(["a", "b"])
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    fake_client.models.embed_content.assert_called_once()


def test_embed_texts_swallows_api_errors():
    fake_client = MagicMock()
    fake_client.models.embed_content.side_effect = RuntimeError("api down")
    with patch.object(store, "get_genai_client", return_value=fake_client):
        result = store.embed_texts(["a"])
    assert result == []


# ---------------------------------------------------------------------------
# get_collection
# ---------------------------------------------------------------------------


def test_get_collection_returns_none_when_chroma_unreachable():
    fake_chromadb = MagicMock()
    fake_chromadb.HttpClient.side_effect = RuntimeError("connection refused")
    with patch.dict("sys.modules", {"chromadb": fake_chromadb}):
        assert store.get_collection() is None


def test_get_collection_caches_collection():
    fake_collection = MagicMock(name="collection")
    fake_client = MagicMock()
    fake_client.get_or_create_collection.return_value = fake_collection
    fake_chromadb = MagicMock()
    fake_chromadb.HttpClient.return_value = fake_client

    with patch.dict("sys.modules", {"chromadb": fake_chromadb}):
        first = store.get_collection()
        second = store.get_collection()

    assert first is fake_collection
    assert second is fake_collection
    # Zweiter Aufruf darf den Client nicht erneut aufbauen.
    fake_chromadb.HttpClient.assert_called_once()
