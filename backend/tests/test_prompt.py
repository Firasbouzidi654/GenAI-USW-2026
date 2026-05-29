from unittest.mock import AsyncMock, MagicMock, patch


def test_prompt_returns_response(client):
    mock_gemini = MagicMock(text="This is a test response")
    with patch("app.api.v1.prompt.client.models.generate_content", return_value=mock_gemini), \
         patch("app.api.v1.prompt.retrieve_context", new_callable=AsyncMock, return_value=""):
        response = client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    assert response.status_code == 200
    assert response.json()["response"] == "This is a test response"


def test_prompt_calls_retriever_with_prompt(client):
    mock_gemini = MagicMock(text="answer")
    with patch("app.api.v1.prompt.client.models.generate_content", return_value=mock_gemini), \
         patch("app.api.v1.prompt.retrieve_context", new_callable=AsyncMock, return_value="") as mock_retriever:
        client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    mock_retriever.assert_called_once_with("Was ist SQL?")


def test_prompt_includes_context_when_available(client):
    mock_gemini = MagicMock(text="answer")
    with patch("app.api.v1.prompt.client.models.generate_content", return_value=mock_gemini) as mock_call, \
         patch("app.api.v1.prompt.retrieve_context", new_callable=AsyncMock, return_value="Kontext aus Skript"):
        client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    full_prompt = mock_call.call_args.kwargs["contents"]
    assert "Kontext aus Skript" in full_prompt
    assert "Was ist SQL?" in full_prompt


def test_prompt_missing_field_returns_422(client):
    response = client.post("/api/prompt", json={})
    assert response.status_code == 422


def test_prompt_gemini_error_returns_502(client):
    with patch("app.api.v1.prompt.client.models.generate_content", side_effect=Exception("Gemini down")), \
         patch("app.api.v1.prompt.retrieve_context", new_callable=AsyncMock, return_value=""):
        response = client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    assert response.status_code == 502


async def async_chunk_generator(*texts):
    for text in texts:
        yield MagicMock(text=text)


def test_stream_prompt_returns_event_stream(client):
    with patch("app.api.v1.prompt.client.aio.models.generate_content_stream",
               new=AsyncMock(return_value=async_chunk_generator("Hallo ", "Welt"))), \
         patch("app.api.v1.prompt.retrieve_context", new_callable=AsyncMock, return_value=""):
        response = client.post("/api/prompt/stream", json={"prompt": "Test"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "data: Hallo " in response.text
    assert "data: Welt" in response.text
    assert "data: [DONE]" in response.text