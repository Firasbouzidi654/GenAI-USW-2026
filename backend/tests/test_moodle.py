"""Tests für den Moodle-Status-Endpunkt (ohne Token → nicht konfiguriert)."""


def test_moodle_status_not_configured(client):
    response = client.get("/api/moodle/status")
    assert response.status_code == 200
    assert response.json() == {"configured": False}


def test_moodle_courses_without_token_returns_503(client):
    response = client.get("/api/moodle/courses")
    assert response.status_code == 503
