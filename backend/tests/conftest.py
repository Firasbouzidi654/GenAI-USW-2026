import os

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://test:test@localhost/test")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)