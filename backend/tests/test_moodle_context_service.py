"""Tests for lightweight Moodle context service and Orchestrator usage."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents import orchestrator
from app.services import moodle_context_service as moodle_context


@pytest.fixture(autouse=True)
def configured_moodle(monkeypatch):
    monkeypatch.setattr(moodle_context.moodle_service, "is_configured", lambda: True)


@pytest.fixture
def unternehmenssoftware_moodle(monkeypatch):
    async def fake_courses():
        return [
            {
                "id": 58776,
                "fullname": "B5.3 Unternehmenssoftware (SL) - 1. Zug + 2. Zug - SoSe2026",
                "shortname": "B5.3 Unternehmenssoftware",
                "semester": "SoSe 2026",
                "visible": True,
            }
        ]

    async def fake_deadlines(course_id):
        assert course_id == "58776"
        return {
            "course_id": 58776,
            "deadlines": [
                {
                    "name": "Submission Presentation 3",
                    "type": "assignment",
                    "section_name": "Session 3",
                    "due_date": "2026-06-30T06:00:00+00:00",
                    "status": "open",
                }
            ],
        }

    async def fake_overview(course_id):
        assert course_id == "58776"
        return [
            {
                "section_name": "Session 1",
                "items": [
                    {"name": "Slides Session 1", "type": "file", "filename": "slides1.pdf"},
                    {"name": "Submission Presentation 1", "type": "assignment"},
                ],
            },
            {
                "section_name": "Session 3",
                "items": [
                    {"name": "Slides Session 3", "type": "file", "filename": "slides3.pdf"},
                    {
                        "name": "Submission Presentation 3",
                        "type": "assignment",
                        "due_date": "2026-06-30T06:00:00+00:00",
                    },
                ],
            },
        ]

    async def fake_grades(course_id):
        assert course_id == "58776"
        return {
            "course_id": 58776,
            "grades": [
                {"name": "Submission Presentation 1", "grade": "90", "percentage": "90%"},
                {"name": "Submission Presentation 3", "grade": "open", "percentage": ""},
                {"name": "Intermediate Presentation", "grade": "85", "percentage": "85%"},
                {"name": "Assessment", "grade": "1.7", "percentage": "85%"},
            ],
        }

    monkeypatch.setattr(moodle_context.moodle_service, "get_moodle_courses", fake_courses)
    monkeypatch.setattr(moodle_context.moodle_service, "get_moodle_course_deadlines", fake_deadlines)
    monkeypatch.setattr(moodle_context.moodle_service, "get_moodle_course_overview", fake_overview)
    monkeypatch.setattr(moodle_context.moodle_service, "get_moodle_course_grades", fake_grades)


@pytest.mark.asyncio
async def test_moodle_context_returns_courses(unternehmenssoftware_moodle):
    result = await moodle_context.get_moodle_courses_context()

    assert "Moodle-Kurse" in result
    assert "B5.3 Unternehmenssoftware" in result
    assert "58776" in result


@pytest.mark.asyncio
async def test_moodle_context_returns_next_deadline(unternehmenssoftware_moodle):
    result = await moodle_context.get_next_moodle_deadline_context("Unternehmenssoftware")

    assert "Submission Presentation 3" in result
    assert "B5.3 Unternehmenssoftware" in result
    assert "30.06.2026, 08:00" in result


@pytest.mark.asyncio
async def test_moodle_context_returns_course_summary(unternehmenssoftware_moodle):
    result = await moodle_context.get_moodle_course_context("Unternehmenssoftware")

    assert "Course ID: 58776" in result
    assert "Session 1" in result
    assert "Slides Session 3" in result
    assert "Submission Presentation 3" in result


@pytest.mark.asyncio
async def test_moodle_context_returns_grades(unternehmenssoftware_moodle):
    result = await moodle_context.get_moodle_grades_context("Unternehmenssoftware")

    assert "Submission Presentation 1" in result
    assert "Submission Presentation 3" in result
    assert "Intermediate Presentation" in result
    assert "Assessment" in result


@pytest.mark.asyncio
async def test_orchestrator_uses_moodle_context_for_explicit_moodle_question(monkeypatch):
    context = AsyncMock(return_value="Naechste Moodle-Aufgabe")
    create_orchestrator = MagicMock()
    monkeypatch.setattr(orchestrator, "get_moodle_context_for_message", context)
    monkeypatch.setattr(orchestrator, "create_orchestrator", create_orchestrator)

    result = await orchestrator.run_orchestrator("Was ist meine nächste Moodle-Aufgabe?", MagicMock())

    assert result == "Naechste Moodle-Aufgabe"
    context.assert_awaited_once()
    create_orchestrator.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_uses_moodle_context_for_explicit_moodle_deadlines(monkeypatch):
    context = AsyncMock(return_value="Moodle-Deadlines fuer Unternehmenssoftware")
    create_orchestrator = MagicMock()
    monkeypatch.setattr(orchestrator, "get_moodle_context_for_message", context)
    monkeypatch.setattr(orchestrator, "create_orchestrator", create_orchestrator)

    result = await orchestrator.run_orchestrator(
        "Zeige mir die Moodle-Deadlines für Unternehmenssoftware.",
        MagicMock(),
    )

    assert result == "Moodle-Deadlines fuer Unternehmenssoftware"
    context.assert_awaited_once()
    create_orchestrator.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_keeps_non_moodle_routing_unchanged(monkeypatch):
    context = AsyncMock(return_value="moodle")
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(return_value={"messages": []})
    monkeypatch.setattr(orchestrator, "get_moodle_context_for_message", context)
    monkeypatch.setattr(orchestrator, "create_orchestrator", MagicMock(return_value=fake_agent))
    monkeypatch.setattr(orchestrator, "extract_text_output", lambda _result: "normal agent answer")

    result = await orchestrator.run_orchestrator("Erklär mir Promises in JavaScript.", MagicMock())

    assert result == "normal agent answer"
    context.assert_not_called()
    fake_agent.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_routes_selected_moodle_session_to_tutor(monkeypatch):
    tutor = AsyncMock(return_value="Session 1 aus Moodle-RAG")
    context = AsyncMock(return_value="moodle context")
    create_orchestrator = MagicMock()
    monkeypatch.setattr(orchestrator, "run_tutor_agent", tutor)
    monkeypatch.setattr(orchestrator, "get_moodle_context_for_message", context)
    monkeypatch.setattr(orchestrator, "create_orchestrator", create_orchestrator)

    moodle_context = {
        "course_id": 58776,
        "course_name": "B5.3 Unternehmenssoftware",
        "sections": [{"section_name": "Session 1", "items": []}],
    }
    result = await orchestrator.run_orchestrator(
        "Explique-moi Session 1",
        MagicMock(),
        chat_id="chat-1",
        user_id="local",
        moodle_context=moodle_context,
    )

    assert result == "Session 1 aus Moodle-RAG"
    tutor.assert_awaited_once()
    assert tutor.call_args.kwargs["moodle_context"] == moodle_context
    context.assert_not_called()
    create_orchestrator.assert_not_called()


@pytest.fixture
def semester_5_moodle(monkeypatch):
    async def fake_courses():
        return [
            {
                "id": 60415,
                "fullname": "AWE Life-Hacking - Die Struktur des Erfolgs - 1. Zug - SoSe2026",
                "shortname": "AWE Life-H-231988-9",
                "semester": "SoSe 2026",
            },
            {
                "id": 59507,
                "fullname": "B5.2 Produktionswirtschaft/Logistik (PCÜ) - 1. Zug, 1. Gruppe - SoSe2026",
                "shortname": "PRODW/LOG-230389-1",
                "semester": "SoSe 2026",
            },
            {
                "id": 58776,
                "fullname": "B5.3 Unternehmenssoftware (SL) - 1. Zug + 2. Zug - SoSe2026",
                "shortname": "USWS-230338-9+10",
                "semester": "SoSe 2026",
            },
            {
                "id": 58690,
                "fullname": "B5.2 Produktionswirtschaft/Logistik (SL) - 1. Zug - SoSe2026",
                "shortname": "PRODW/LOG-230106-9",
                "semester": "SoSe 2026",
            },
            {
                "id": 40001,
                "fullname": "B3.1 Webtechnologien (SL) - 1. Zug + 2. Zug - SoSe2026",
                "shortname": "WEBTECH-OLD",
                "semester": "SoSe 2026",
            },
        ]

    async def fake_deadlines(course_id):
        deadlines_by_course = {
            "60415": [],
            "59507": [],
            "58690": [],
            "58776": [
                {
                    "name": "Submission Presentation 1",
                    "due_date": "2026-06-02T06:00:00+00:00",
                },
                {
                    "name": "Intermediate Presentation",
                    "due_date": "2026-06-16T06:00:00+00:00",
                },
                {
                    "name": "Submission Presentation 3",
                    "due_date": "2026-06-30T06:00:00+00:00",
                },
            ],
            "40001": [
                {
                    "name": "Finale Projektabgabe",
                    "due_date": "2026-07-05T21:59:00+00:00",
                }
            ],
        }
        return {"course_id": int(course_id), "deadlines": deadlines_by_course.get(course_id, [])}

    monkeypatch.setattr(moodle_context.moodle_service, "get_moodle_courses", fake_courses)
    monkeypatch.setattr(moodle_context.moodle_service, "get_moodle_course_deadlines", fake_deadlines)


@pytest.mark.asyncio
async def test_global_next_moodle_deadline_across_all_courses(semester_5_moodle):
    result = await moodle_context.get_moodle_context_for_message("Was ist meine nächste Moodle-Aufgabe?")

    assert "Submission Presentation 3" in result
    assert "B5.3 Unternehmenssoftware" in result
    assert "30.06.2026, 08:00" in result
    assert "Finale Projektabgabe" not in result
    assert "AWE Life-Hacking" not in result


@pytest.mark.asyncio
async def test_moodle_deadlines_by_course_group_past_and_upcoming(semester_5_moodle):
    result = await moodle_context.get_moodle_context_for_message(
        "Zeige mir die Moodle-Deadlines für Unternehmenssoftware."
    )

    assert "Moodle-Deadlines für B5.3 Unternehmenssoftware" in result
    assert "Bereits vergangen:" in result
    assert "Submission Presentation 1 — 02.06.2026, 08:00" in result
    assert "Intermediate Presentation — 16.06.2026, 08:00" in result
    assert "Anstehend:" in result
    assert "Submission Presentation 3 — 30.06.2026, 08:00" in result
    assert "Klausur Unternehmenssoftware" not in result


@pytest.mark.asyncio
async def test_orchestrator_exact_moodle_deadlines_question_uses_moodle_data_only(
    semester_5_moodle,
    monkeypatch,
):
    create_orchestrator = MagicMock()
    monkeypatch.setattr(orchestrator, "create_orchestrator", create_orchestrator)

    result = await orchestrator.run_orchestrator(
        "Zeige mir die Moodle-Deadlines für Unternehmenssoftware.",
        MagicMock(),
    )

    create_orchestrator.assert_not_called()
    assert "Submission Presentation 1" in result
    assert "Intermediate Presentation" in result
    assert "Submission Presentation 3" in result
    assert "Klausur Unternehmenssoftware" not in result


@pytest.mark.asyncio
async def test_orchestrator_next_moodle_task_uses_moodle_data_only(
    semester_5_moodle,
    monkeypatch,
):
    create_orchestrator = MagicMock()
    monkeypatch.setattr(orchestrator, "create_orchestrator", create_orchestrator)

    result = await orchestrator.run_orchestrator(
        "Welche Moodle-Aufgabe kommt als Nächstes?",
        MagicMock(),
    )

    create_orchestrator.assert_not_called()
    assert "Submission Presentation 3" in result
    assert "30.06.2026, 08:00" in result
    assert "Klausur" not in result


@pytest.mark.asyncio
async def test_non_moodle_calendar_deadlines_keep_normal_routing(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(return_value={"messages": []})
    create_orchestrator = MagicMock(return_value=fake_agent)
    context = AsyncMock(return_value="moodle")
    monkeypatch.setattr(orchestrator, "create_orchestrator", create_orchestrator)
    monkeypatch.setattr(orchestrator, "get_moodle_context_for_message", context)
    monkeypatch.setattr(orchestrator, "extract_text_output", lambda _result: "calendar/planner answer")

    result = await orchestrator.run_orchestrator("Welche Deadlines habe ich im Kalender?", MagicMock())

    assert result == "calendar/planner answer"
    context.assert_not_called()
    create_orchestrator.assert_called_once()


@pytest.mark.asyncio
async def test_non_moodle_exam_question_keeps_normal_routing(monkeypatch):
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(return_value={"messages": []})
    create_orchestrator = MagicMock(return_value=fake_agent)
    context = AsyncMock(return_value="moodle")
    monkeypatch.setattr(orchestrator, "create_orchestrator", create_orchestrator)
    monkeypatch.setattr(orchestrator, "get_moodle_context_for_message", context)
    monkeypatch.setattr(orchestrator, "extract_text_output", lambda _result: "exam/planner answer")

    result = await orchestrator.run_orchestrator("Welche Prüfung habe ich als Nächstes?", MagicMock())

    assert result == "exam/planner answer"
    context.assert_not_called()
    create_orchestrator.assert_called_once()


@pytest.mark.asyncio
async def test_semester_5_filtering_excludes_webtechnologien(semester_5_moodle):
    result = await moodle_context.get_moodle_context_for_message("Welche Moodle-Module habe ich für 5. Semester?")

    assert "AWE Life-Hacking" in result
    assert "B5.3 Unternehmenssoftware" in result
    assert "PRODW/LOG-230389-1" in result
    assert "PRODW/LOG-230106-9" in result
    assert "Webtechnologien" not in result
    assert "40001" not in result


@pytest.fixture
def semester_4_moodle(monkeypatch):
    async def fake_courses():
        return [
            {
                "id": 41001,
                "fullname": "Investition und Finanzierung - 1. Zug - WiSe2025",
                "shortname": "INVFIN-41001",
                "semester": "WiSe 2025/26",
            },
            {
                "id": 41002,
                "fullname": "Konfliktmanagement - 1. Zug - WiSe2025",
                "shortname": "KONFLIKT-41002",
                "semester": "WiSe 2025/26",
            },
            {
                "id": 40001,
                "fullname": "B3.1 Webtechnologien (SL) - 1. Zug + 2. Zug - SoSe2026",
                "shortname": "WEBTECH-OLD",
                "semester": "SoSe 2026",
            },
            {
                "id": 58776,
                "fullname": "B5.3 Unternehmenssoftware (SL) - 1. Zug + 2. Zug - SoSe2026",
                "shortname": "USWS-230338-9+10",
                "semester": "SoSe 2026",
            },
        ]

    monkeypatch.setattr(moodle_context.moodle_service, "get_moodle_courses", fake_courses)


@pytest.mark.asyncio
async def test_semester_4_filtering_uses_hardcoded_mapping_and_excludes_other_semesters(semester_4_moodle):
    result = await moodle_context.get_moodle_context_for_message(
        "Welche Moodle-Module habe ich für das 4. Semester?"
    )

    assert "Moodle-Kurse fuer Semester 4" in result
    assert "Investition und Finanzierung" in result
    assert "Konfliktmanagement" in result
    assert "Webtechnologien" not in result
    assert "Unternehmenssoftware" not in result


@pytest.mark.asyncio
async def test_moodle_due_date_is_displayed_in_europe_berlin_time(semester_5_moodle):
    result = await moodle_context.get_next_moodle_deadline_context("Unternehmenssoftware")

    assert "30.06.2026, 08:00" in result
    assert "30.06.2026, 06:00" not in result
