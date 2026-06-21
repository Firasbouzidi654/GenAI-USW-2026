"""Tests für den LSF-Mock und den LSF→DB-Sync."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.api.v1.lsf_mock import get_grades, get_termine
from app.models.academic_event import AcademicEvent
from app.models.calendar_event import CalendarEvent
from app.models.exam import Exam
from app.models.grade import Grade
from app.services.lsf_sync import sync_lsf_to_db


def test_lsf_profile_returns_student(client):
    response = client.get("/api/lsf/profile")
    assert response.status_code == 200
    data = response.json()
    assert data["student_name"] == "Erika Musterfrau"
    assert "matrikelnummer" in data


def test_lsf_grades_returns_list(client):
    response = client.get("/api/lsf/grades")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list) and len(data) >= 1
    assert "module_name" in data[0] and "grade" in data[0] and "status" in data[0]
    assert "ects" in data[0] and "type" in data[0]


def test_lsf_termine_returns_list(client):
    response = client.get("/api/lsf/termine")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list) and len(data) >= 1
    assert "title" in data[0] and "type" in data[0] and "date" in data[0]


def test_lsf_exams_returns_only_exams(client):
    response = client.get("/api/lsf/exams")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert all(t["type"] == "EXAM" for t in data)


def test_termine_contain_all_expected_types():
    types = {t.type for t in get_termine()}
    # Vorlesungen, Prüfungen, Abgaben, Präsentationen sind vertreten
    assert "EXAM" in types
    assert "ASSIGNMENT" in types
    assert "PRESENTATION" in types
    assert types & {"LECTURE", "SEMINAR", "EXERCISE"}


def test_grades_are_well_formed():
    grades = get_grades()
    assert len(grades) >= 1
    for g in grades:
        assert g.module_name
        assert g.ects > 0


def test_sync_maps_lsf_to_db_tables():
    """Sync schreibt Grade/CalendarEvent/AcademicEvent/Exam in der erwarteten Menge."""
    added = []

    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock(side_effect=lambda obj: added.append(obj))

    result = asyncio.run(sync_lsf_to_db(db))

    assert result["synced"] is True

    grades = [o for o in added if isinstance(o, Grade)]
    calendar = [o for o in added if isinstance(o, CalendarEvent)]
    planner = [o for o in added if isinstance(o, AcademicEvent)]
    exams = [o for o in added if isinstance(o, Exam)]

    assert len(grades) == result["grades"] >= 1
    assert len(calendar) == result["calendar_events"] >= 1
    assert len(planner) == result["planner_events"] >= 1
    assert len(exams) == result["exams"] >= 1
    # Jede Prüfung erzeugt sowohl einen Planner- als auch einen Exam-Eintrag
    assert len(exams) <= len(planner)
    # delete() wurde für den idempotenten Replace aufgerufen
    assert db.execute.await_count >= 4
    db.commit.assert_awaited()
