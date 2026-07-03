def _route_paths(app):
    return {getattr(route, "path", "") for route in app.routes}


def test_frontend_curriculum_routes_are_registered(client):
    paths = _route_paths(client.app)

    assert "/api/curriculum" in paths
    assert "/api/curriculum/status" in paths
    assert "/api/curriculum/upload" in paths
    assert "/api/curriculum/suggest-module" in paths


def test_curriculum_status_contract(client):
    response = client.get("/api/curriculum/status")

    assert response.status_code == 200
    assert set(response.json()) == {"processing", "modules", "with_prerequisites"}


def test_study_plan_rejects_invalid_horizon(client):
    response = client.post("/api/planner/study-plan", json={"horizon_days": 0})

    assert response.status_code == 422


def test_calendar_event_rejects_blank_title(client):
    response = client.post(
        "/api/calendar/events",
        json={
            "title": "   ",
            "start_time": "2026-07-03T10:00:00+02:00",
            "end_time": "2026-07-03T11:00:00+02:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Titel darf nicht leer sein."


def test_calendar_event_rejects_end_before_start(client):
    response = client.post(
        "/api/calendar/events",
        json={
            "title": "Study block",
            "start_time": "2026-07-03T11:00:00+02:00",
            "end_time": "2026-07-03T10:00:00+02:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Ende muss nach dem Start liegen."


def test_study_advisor_rejects_blank_message(client):
    response = client.post("/api/ai/study-advisor", json={"message": "   "})

    assert response.status_code == 422


def test_evaluator_rejects_blank_message(client):
    response = client.post("/api/ai/evaluate", json={"message": "   "})

    assert response.status_code == 422
