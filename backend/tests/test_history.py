from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.database import get_db
from app.main import app


def _make_message(id, prompt, response):
    msg = MagicMock()
    msg.id = id
    msg.prompt = prompt
    msg.response = response
    msg.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return msg


def _db_override(execute_result=None, execute_error=None):
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()
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


def test_history_returns_messages(client):
    messages = [_make_message(2, "Frage 2", "Antwort 2"), _make_message(1, "Frage 1", "Antwort 1")]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = messages
    app.dependency_overrides[get_db] = _db_override(execute_result=mock_result)

    response = client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["prompt"] == "Frage 2"
    assert data[1]["prompt"] == "Frage 1"


def test_history_db_error_returns_503(client):
    app.dependency_overrides[get_db] = _db_override(execute_error=Exception("DB down"))

    response = client.get("/api/history")
    assert response.status_code == 503