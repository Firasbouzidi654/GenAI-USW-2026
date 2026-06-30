import pytest

from app.agents import career_agent


def test_career_analysis_parses_groq_failed_generation_json():
    error_text = (
        "Error code: 400 - {'error': {'code': 'tool_use_failed', "
        "'failed_generation': '<function=_CareerAnalysisSchema> "
        '{"summary":"Analyse","confidence_percent":80,"job_fit_percent":70,'
        '"skills":[{"name":"Datenbanken","score":5,"percent":90,'
        '"reason":"Gute DB-Noten","matched_courses":["Datenbanktechnologien"]}],'
        '"roles":[{"title":"Data Engineer","match_percent":85,'
        '"reason":"Starke Datenbankkenntnisse","missing_skills":["Cloud"],'
        '"recommended_certifications":["AWS Cloud Practitioner"],'
        '"recommended_projects":["ETL Pipeline"],"market_demand":"High",'
        '"salary_range_eur":"EUR 55.000 - EUR 75.000 pro Jahr"}],'
        '"strengths":["Datenbanken"],"weak_areas":["Cloud"],'
        '"recommended_learning_path":["Cloud Grundlagen"]}'
        "'}}"
    )

    result = career_agent._analysis_from_json_text(error_text)

    assert result is not None
    assert result.summary == "Analyse"
    assert result.skills[0].name == "Datenbanken"
    assert result.roles[0].title == "Data Engineer"


@pytest.mark.asyncio
async def test_career_analysis_uses_failed_generation_json_when_structured_output_fails(monkeypatch):
    async def fake_fallback(_invoke, temperature=0.0):
        raise RuntimeError(
            '<function=_CareerAnalysisSchema> '
            '{"summary":"Analyse","confidence_percent":75,"job_fit_percent":65,'
            '"skills":[{"name":"Web","score":4,"percent":80,"reason":"Webkurs",'
            '"matched_courses":["Webtechnologien"]}],'
            '"roles":[{"title":"Frontend Developer","match_percent":80,'
            '"reason":"Webtechnologien","missing_skills":[],"recommended_certifications":[],'
            '"recommended_projects":["Portfolio"],"market_demand":"High",'
            '"salary_range_eur":"EUR 45.000 - EUR 65.000 pro Jahr"}],'
            '"strengths":["Web"],"weak_areas":[],"recommended_learning_path":["Vue vertiefen"]}'
        )

    monkeypatch.setattr(career_agent, "run_with_model_fallback", fake_fallback)

    result = await career_agent.get_ai_career_analysis(
        [{"course_name": "Webtechnologien", "grade": "1.0", "credits": 5}]
    )

    assert result["summary"] == "Analyse"
    assert result["skills"][0]["matched_courses"] == [
        {"course_name": "Webtechnologien", "grade": "1.0"}
    ]
    assert result["roles"][0]["title"] == "Frontend Developer"
