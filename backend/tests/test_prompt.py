"""Tests für den /api/prompt Endpunkt (TutorAgent-basiert)."""

from unittest.mock import AsyncMock, patch

# Der Mock muss am Verwendungsort (prompt.py) gesetzt werden, nicht in tutor_agent.py
_MOCK_TARGET = "app.api.v1.prompt.run_orchestrator"


def test_prompt_returns_event_stream(client):
    with patch(_MOCK_TARGET, new=AsyncMock(return_value="Hallo Welt")):
        response = client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "Hallo" in response.text
    assert "data: [DONE]" in response.text


def test_prompt_missing_field_returns_422(client):
    response = client.post("/api/prompt", json={})
    assert response.status_code == 422


def test_prompt_blank_prompt_returns_422(client):
    response = client.post("/api/prompt", json={"prompt": "   "})
    assert response.status_code == 422


def test_prompt_unsafe_chat_id_returns_422(client):
    response = client.post(
        "/api/prompt",
        json={"prompt": "Was ist SQL?", "chat_id": "../outside"},
    )
    assert response.status_code == 422


def test_prompt_agent_error_yields_error_event(client):
    with patch(_MOCK_TARGET, new=AsyncMock(side_effect=Exception("Agent down"))):
        response = client.post("/api/prompt", json={"prompt": "Was ist SQL?"})
    assert response.status_code == 200
    assert "[ERROR]" in response.text


def test_prompt_passes_message_to_agent(client):
    mock_agent = AsyncMock(return_value="Eine Antwort")
    with patch(_MOCK_TARGET, new=mock_agent):
        client.post("/api/prompt", json={"prompt": "Erkläre mir Rekursion"})
    mock_agent.assert_called_once()
    assert mock_agent.call_args[0][0] == "Erkläre mir Rekursion"


def test_prompt_general_question_does_not_process_pdfs(client):
    mock_agent = AsyncMock(return_value="Promises erklärt")
    with patch(_MOCK_TARGET, new=mock_agent), \
         patch("app.rag.pipeline.process_document_sync") as process_pdf, \
         patch("app.services.moodle_service.index_course_by_name", new=AsyncMock()) as index_moodle:
        response = client.post("/api/prompt", json={"prompt": "Erklär mir Promises in JavaScript."})

    assert response.status_code == 200
    process_pdf.assert_not_called()
    index_moodle.assert_not_awaited()

def test_prompt_passes_moodle_context_to_orchestrator(client):
    mock_agent = AsyncMock(return_value="Session answer")
    moodle_context = {
        "course_id": 58776,
        "course_name": "B5.3 Unternehmenssoftware",
        "sections": [{"section_name": "Session 1", "items": []}],
    }
    with patch(_MOCK_TARGET, new=mock_agent):
        response = client.post(
            "/api/prompt",
            json={
                "prompt": "Explique-moi Session 1",
                "chat_id": "chat-1",
                "moodle_context": moodle_context,
            },
        )

    assert response.status_code == 200
    mock_agent.assert_called_once()
    assert mock_agent.call_args.kwargs["moodle_context"] == moodle_context
