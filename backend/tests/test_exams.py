from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.database import get_db
from app.main import app


def _make_exam(id, subject, exam_date):
    exam = MagicMock()
    exam.id = id
    exam.subject = subject
    exam.exam_date = exam_date
    exam.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return exam


def _db_override(execute_result=None, execute_error=None):
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()
    if execute_error:
        mock_db.execute = AsyncMock(side_effect=execute_error)
    else:
        mock_db.execute = AsyncMock(return_value=execute_result)

    async def override():
        yield mock_db

    return override


@pytest.fixture(autouse=True)
def restore_db_override():
    yield
    async def default():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session
    app.dependency_overrides[get_db] = default


def test_get_exams_returns_list(client):
    exams = [_make_exam(1, "Datenbanken", date(2025, 6, 15))]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = exams
    app.dependency_overrides[get_db] = _db_override(execute_result=mock_result)

    response = client.get("/api/exams")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["subject"] == "Datenbanken"
    assert data[0]["exam_date"] == "2025-06-15"


def test_create_exam_returns_201(client):
    async def mock_refresh(obj):
        obj.id = 1
        obj.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=mock_refresh)
    mock_db.execute = AsyncMock()

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override

    response = client.post("/api/exams", json={"subject": "Statistik", "exam_date": "2025-06-22"})
    assert response.status_code == 201
    assert response.json()["subject"] == "Statistik"


def test_delete_exam_returns_204(client):
    exam = _make_exam(1, "Statistik", date(2025, 6, 22))
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = exam
    app.dependency_overrides[get_db] = _db_override(execute_result=mock_result)

    response = client.delete("/api/exams/1")
    assert response.status_code == 204


def test_delete_exam_not_found_returns_404(client):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    app.dependency_overrides[get_db] = _db_override(execute_result=mock_result)

    response = client.delete("/api/exams/99")
    assert response.status_code == 404


def test_get_exams_db_error_returns_503(client):
    app.dependency_overrides[get_db] = _db_override(execute_error=Exception("DB down"))

    response = client.get("/api/exams")
    assert response.status_code == 503