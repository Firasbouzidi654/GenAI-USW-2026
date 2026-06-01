from unittest.mock import AsyncMock, MagicMock, patch


async def async_chunk_generator(*texts):
    for text in texts:
        yield MagicMock(text=text)


def test_prompt_returns_event_stream(client):
    with patch("app.api.v1.prompt.client.aio.models.generate_content_stream",
               new=AsyncMock(return_value=async_chunk_generator("Hallo ", "Welt"))), \
         patch("app.api.v1.prompt.retrieve_context", new_callable=AsyncMock, return_value=""):
        response = client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert 'data: "Hallo "' in response.text
    assert 'data: "Welt"' in response.text
    assert "data: [DONE]" in response.text


def test_prompt_calls_retriever_with_prompt(client):
    with patch("app.api.v1.prompt.client.aio.models.generate_content_stream",
               new=AsyncMock(return_value=async_chunk_generator("answer"))), \
         patch("app.api.v1.prompt.retrieve_context", new_callable=AsyncMock, return_value="") as mock_retriever:
        client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    mock_retriever.assert_called_once_with("Was ist SQL?")


def test_prompt_includes_context_when_available(client):
    mock_stream = AsyncMock(return_value=async_chunk_generator("answer"))
    with patch("app.api.v1.prompt.client.aio.models.generate_content_stream", new=mock_stream), \
         patch("app.api.v1.prompt.retrieve_context", new_callable=AsyncMock, return_value="Kontext aus Skript"):
        client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    full_prompt = mock_stream.call_args.kwargs["contents"]
    assert "Kontext aus Skript" in full_prompt
    assert "Was ist SQL?" in full_prompt


def test_prompt_missing_field_returns_422(client):
    response = client.post("/api/prompt", json={})
    assert response.status_code == 422


def test_prompt_gemini_error_yields_error_event(client):
    with patch("app.api.v1.prompt.client.aio.models.generate_content_stream",
               new=AsyncMock(side_effect=Exception("Gemini down"))), \
         patch("app.api.v1.prompt.retrieve_context", new_callable=AsyncMock, return_value=""):
        response = client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    assert response.status_code == 200
    assert "data: [ERROR]" in response.text
