def test_moodle_modules_returns_list(client):
    response = client.get("/api/moodle/modules")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["name"] == "Datenbanken"
    assert "semester" in data[0]
    assert "credits" in data[0]


def test_moodle_grades_returns_list(client):
    response = client.get("/api/moodle/grades")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1
    assert "module_name" in data[0]
    assert "grade" in data[0]
    assert "status" in data[0]


def test_moodle_events_returns_list(client):
    response = client.get("/api/moodle/events")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1
    assert "title" in data[0]
    assert "type" in data[0]
    assert "date" in data[0]


def test_moodle_exams_returns_only_exams(client):
    response = client.get("/api/moodle/exams")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 1
    assert all(event["type"] == "EXAM" for event in data)