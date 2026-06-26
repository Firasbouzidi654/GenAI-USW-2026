"""Tests fuer Moodle-Endpunkte und Overview-Transformation."""

import pytest

from app.services import moodle_service


def test_moodle_status_not_configured(client):
    response = client.get("/api/moodle/status")
    assert response.status_code == 200
    assert response.json() == {"configured": False}


def test_moodle_courses_without_token_returns_503(client):
    response = client.get("/api/moodle/courses")
    assert response.status_code == 503


def test_moodle_course_content_without_token_returns_503(client):
    response = client.get("/api/moodle/course/123/content")
    assert response.status_code == 503
    assert "MOODLE_TOKEN" in response.json()["detail"]


def test_moodle_course_overview_without_token_returns_503(client):
    response = client.get("/api/moodle/course/123/overview")
    assert response.status_code == 503
    assert "MOODLE_TOKEN" in response.json()["detail"]


def test_moodle_course_grades_without_token_returns_503(client):
    response = client.get("/api/moodle/course/123/grades")
    assert response.status_code == 503
    assert "MOODLE_TOKEN" in response.json()["detail"]


@pytest.mark.asyncio
async def test_moodle_courses_transform(monkeypatch):
    async def fake_user_id():
        return 7

    async def fake_call(wsfunction, **params):
        assert wsfunction == "core_enrol_get_users_courses"
        assert params["userid"] == 7
        return [
            {
                "id": 123,
                "fullname": "Webtechnologien",
                "shortname": "B3.1 WebTech",
                "visible": True,
                "startdate": 0,
            }
        ]

    monkeypatch.setattr(moodle_service, "get_moodle_user_id", fake_user_id)
    monkeypatch.setattr(moodle_service, "_call", fake_call)

    courses = await moodle_service.get_moodle_courses()

    assert courses == [
        {
            "id": 123,
            "shortname": "B3.1 WebTech",
            "fullname": "Webtechnologien",
            "visible": True,
            "semester": "Unbekanntes Semester",
            "startdate": 0,
        }
    ]


@pytest.mark.asyncio
async def test_moodle_course_overview_transforms_sections(monkeypatch):
    monkeypatch.setattr(moodle_service.settings, "moodle_token", "test-token")

    async def fake_content(_course_id):
        return [
            {
                "name": "Session 1",
                "modules": [
                    {
                        "name": "Slides Session 1",
                        "modname": "resource",
                        "contents": [
                            {
                                "type": "file",
                                "filename": "slides.pdf",
                                "fileurl": "https://example.test/slides.pdf?forcedownload=1",
                                "mimetype": "application/pdf",
                                "filesize": 2048,
                            }
                        ],
                    },
                    {
                        "name": "Python Exercises",
                        "modname": "url",
                        "url": "https://example.test/exercises",
                    },
                    {
                        "name": "Submission Presentation 1",
                        "modname": "assign",
                        "dates": [{"label": "Due date", "timestamp": 1893456000}],
                    },
                ],
            }
        ]

    monkeypatch.setattr(moodle_service, "get_moodle_course_content", fake_content)

    overview = await moodle_service.get_moodle_course_overview("42")

    assert overview[0]["section_name"] == "Session 1"
    assert overview[0]["items"][0]["type"] == "file"
    assert overview[0]["items"][0]["filename"] == "slides.pdf"
    assert overview[0]["items"][0]["open_url"] == "https://example.test/slides.pdf?forcedownload=1&token=test-token"
    assert overview[0]["items"][1]["type"] == "url"
    assert overview[0]["items"][2]["type"] == "assignment"
    assert overview[0]["items"][2]["due_date"]


@pytest.mark.asyncio
async def test_moodle_course_grades_transform(monkeypatch):
    async def fake_user_id():
        return 7

    async def fake_call(wsfunction, **params):
        assert wsfunction == "gradereport_user_get_grade_items"
        assert params == {"courseid": "123", "userid": 7}
        return {
            "usergrades": [
                {
                    "gradeitems": [
                        {
                            "itemname": "Quiz 1",
                            "itemmodule": "quiz",
                            "gradeformatted": "1.7",
                            "grademaxformatted": "100",
                            "percentageformatted": "85%",
                            "feedback": "<p>Good work</p>",
                        }
                    ]
                }
            ]
        }

    monkeypatch.setattr(moodle_service, "get_moodle_user_id", fake_user_id)
    monkeypatch.setattr(moodle_service, "_call", fake_call)

    result = await moodle_service.get_moodle_course_grades("123")

    assert result == {
        "course_id": 123,
        "grades": [
            {
                "name": "Quiz 1",
                "type": "quiz",
                "grade": "1.7",
                "max_grade": "100",
                "percentage": "85%",
                "feedback": "Good work",
            }
        ],
    }


def test_add_token_to_url_handles_urls_without_query():
    result = moodle_service.add_token_to_url("https://example.test/file.pdf", "abc")
    assert result == "https://example.test/file.pdf?token=abc"


def test_add_token_to_url_handles_urls_with_query():
    result = moodle_service.add_token_to_url(
        "https://example.test/file.pdf?forcedownload=1", "abc"
    )
    assert result == "https://example.test/file.pdf?forcedownload=1&token=abc"
