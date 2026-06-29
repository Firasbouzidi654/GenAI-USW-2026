"""Tests for keeping internal agent/tool JSON out of user-visible answers."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents import planner_agent
from app.agents.base import extract_text_output


def test_extract_text_output_ignores_tool_json():
    result = {
        "messages": [
            HumanMessage(content="Worauf sollte ich mich diese Woche konzentrieren?"),
            ToolMessage(
                content='[{"course": "Datenbanktechnologien", "grade": "2.7"}]',
                tool_call_id="grades-1",
            ),
        ]
    }

    assert extract_text_output(result) == ""


def test_extract_text_output_returns_last_assistant_message_after_tools():
    result = {
        "messages": [
            HumanMessage(content="Create a study plan"),
            ToolMessage(content='[{"course": "Webtechnologien"}]', tool_call_id="grades-1"),
            AIMessage(content="Hier ist dein Lernplan fuer diese Woche."),
        ]
    }

    assert extract_text_output(result) == "Hier ist dein Lernplan fuer diese Woche."


def test_planner_tool_fallback_formats_grade_json_naturally():
    payload = [
        {
            "course": "Einführung in die Wirtschaftsinformatik",
            "grade": "3.0",
            "needs_attention": False,
            "good": False,
            "semester": "SS24",
            "credits": 5,
        },
        {
            "course": "Datenbanktechnologien",
            "grade": "2.7",
            "needs_attention": False,
            "good": False,
            "semester": "SS25",
            "credits": 5,
        },
        {
            "course": "Webtechnologien",
            "grade": "1.0",
            "needs_attention": False,
            "good": True,
            "semester": "SS25",
            "credits": 5,
        },
    ]
    result = {
        "messages": [
            HumanMessage(content="Worauf sollte ich mich diese Woche konzentrieren?"),
            ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id="grades-1",
            ),
        ]
    }

    answer = planner_agent._format_planner_tool_fallback(result)

    assert not answer.lstrip().startswith("[")
    assert "Einführung in die Wirtschaftsinformatik" in answer
    assert "Datenbanktechnologien" in answer
    assert "Vorschlag fuer deinen Fokus" in answer


def test_planner_raw_json_fallback_formats_assistant_json_echo():
    raw = json.dumps(
        [{"course": "Grundlagen der Programmierung", "grade": "2.7", "good": False}],
        ensure_ascii=False,
    )

    answer = planner_agent._format_raw_json_fallback(raw)

    assert not answer.lstrip().startswith("[")
    assert "Grundlagen der Programmierung" in answer
