from unittest.mock import MagicMock

import pytest

from app.agents import tutor_agent


def _failed_generation_text() -> str:
    return (
        "Error code: 400 - {'error': {'message': 'tool call validation failed', "
        "'code': 'tool_use_failed', "
        "'failed_generation': '<function=_QuizSchema> "
        '{"title":"USW 2026 WS Session 02","questions":['
        '{"type":"MC","question":"Welche Rekursionstiefe wird im Beispiel genannt?",'
        '"correct_answer":"10","options":["5","10","15","20"]},'
        '{"type":"TF","question":"Eine Session kann mehrere Schritte enthalten.",'
        '"correct_answer":"true"}'
        "]}</function>'}}"
    )


def test_quiz_payload_from_groq_failed_generation_adds_missing_schema_fields():
    payload = tutor_agent._quiz_payload_from_json_text(_failed_generation_text())

    assert payload is not None
    assert payload["title"] == "USW 2026 WS Session 02"
    assert payload["questions"][0]["correct_answer"] == "B"
    assert payload["questions"][0]["explanation"]
    assert payload["questions"][1]["options"] is None
    assert payload["questions"][1]["explanation"]


@pytest.mark.asyncio
async def test_generate_quiz_uses_failed_generation_json_when_structured_output_fails(monkeypatch):
    async def fake_retrieve_context(*_args, **_kwargs):
        return "[Quelle 1]\nSession-Kontext"

    async def fake_model_fallback(_invoke, temperature=0.0):
        raise RuntimeError(_failed_generation_text())

    monkeypatch.setattr(tutor_agent, "retrieve_context", fake_retrieve_context)
    monkeypatch.setattr(tutor_agent, "run_with_model_fallback", fake_model_fallback)

    result = await tutor_agent.generate_quiz_with_agent(
        ["USW_2026_WS_Session_02.pptx"],
        2,
        MagicMock(),
    )

    assert result["title"] == "USW 2026 WS Session 02"
    assert len(result["questions"]) == 2
    assert result["questions"][0]["correct_answer"] == "B"
    assert result["questions"][0]["explanation"]
