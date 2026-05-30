import os

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://test:test@localhost/test")

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db


async def mock_get_db():
    session = MagicMock()
    session.commit = AsyncMock()
    yield session


app.dependency_overrides[get_db] = mock_get_db


@pytest.fixture
def client():
    return TestClient(app)