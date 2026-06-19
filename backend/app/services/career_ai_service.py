"""Career AI Service — Gemini-powered career profile analysis.

Sends the student's stored courses/grades to Gemini and asks it to freely infer skills,
tools, technologies, and the best-matching job roles — no fixed/predefined skill or role
list. This is intentional: an LLM can recognize whatever a course actually teaches (a new
course type, a niche tool, an unusual specialization) without code changes, which a
hardcoded keyword-matching system never could.

The response is strictly validated; any malformed or missing field raises RuntimeError so
the caller (app/api/v1/career.py) can surface a clear error instead of silently failing.
"""

from __future__ import annotations

import json
import logging
import re

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.gemini_api_key)

_SYSTEM_PROMPT = """
You are an AI career advisor analyzing a university student's academic transcript to build a
personalized career profile.

You will receive the student's completed courses/modules, each with a course name, a
German-scale grade (1.0 = best, 5.0 = fail; "no grade recorded" means ungraded/pass-only),
and ECTS credits where known.

Freely infer the skills, tools, and technologies implied by the actual course content — do
NOT limit yourself to a fixed or predefined list. Base every skill strictly on what the
course names and grades actually suggest. Include both technical skills/tools (e.g. SQL,
Python, Power BI, a specific framework or platform) and business/soft skills (e.g. Project
Management, Marketing, Financial Accounting) wherever the coursework genuinely supports them.

Analyze:
- Academic strengths (skills/subjects where the student performs well)
- Weak areas (skills/subjects where the student struggles, or where evidence is thin)
- The specific technical and business skills/tools/technologies evidenced by the transcript
- The best-matching job roles given this profile — choose realistic, specific job titles that
  genuinely fit the evidence, not a fixed list of roles

Respond ONLY with valid JSON in this exact schema:
{
  "summary": "string - 2 to 3 sentences summarizing the student's overall academic profile and which career direction(s) it best supports",
  "confidence_percent": number (0-100, how confident YOU are in this analysis given how much and how clearly relevant the grade data is — fewer or more ambiguous courses should mean lower confidence),
  "job_fit_percent": number (0-100, overall employability/fit given the transcript),
  "skills": [
    {
      "name": "string - a specific skill, tool, or technology inferred from the coursework (e.g. SQL, Python, Power BI, Agile Project Management, Financial Accounting, Cloud Computing, UX Design, ...)",
      "score": number (0-5, integer star rating),
      "percent": number (0-100),
      "reason": "string - one short sentence citing which course(s)/grades support this score",
      "matched_courses": ["string", ...]
    }
  ],
  "roles": [
    {
      "title": "string - a specific, realistic job role title that fits this profile",
      "match_percent": number (0-100, the Job Match),
      "reason": "string - one short, specific explanation of WHY this role matches, grounded in the student's actual grades and courses",
      "missing_skills": ["string", ...] — the most important SPECIFIC missing skills/tools/technologies for this exact role that the transcript does not yet cover (e.g. real tool/platform names like "Azure", "Docker", "Apache Spark", "Kafka", "ETL Pipelines", "CI/CD", "Linux" — not vague categories),
      "recommended_certifications": ["string", ...] — 2 to 4 REAL, specific, well-known certifications that would close the missing-skills gap for this role (e.g. "Microsoft Azure Fundamentals (AZ-900)", "AWS Certified Cloud Practitioner", "PL-300: Microsoft Power BI Data Analyst", "Google Data Analytics Professional Certificate", "Docker Certified Associate"),
      "recommended_projects": ["string", ...] — 2 to 3 concrete, specific portfolio project ideas that would directly demonstrate readiness for this role (e.g. "Build an ETL pipeline that loads sales data into a warehouse", "Create a Power BI dashboard analyzing your university's exam results", "Develop and deploy a REST API with FastAPI"),
      "market_demand": "Very High" | "High" | "Medium" | "Low" — your best estimate of current job-market demand for this role, doesn't need to be precise,
      "salary_range_eur": "string - your best estimate of a typical ANNUAL gross salary range for this role in Germany, formatted exactly like '€55,000 – €75,000 per year'; a rough estimate is fine"
    }
  ],
  "strengths": ["string", ...],
  "weak_areas": ["string", ...],
  "recommended_learning_path": ["string", ...]
}

Rules:
- Identify between 5 and 10 skills/tools/technologies, ranked by how strongly the transcript
  supports them — choose whichever are actually relevant to THIS student's courses, not a
  fixed checklist. Different transcripts should be able to produce entirely different skill
  lists.
- Never invent a skill with no supporting reasoning from the actual coursework.
- Only list a skill the transcript doesn't support if it's a clearly relevant gap for one of
  the recommended roles — in that case give it score 0 and an empty "matched_courses".
- For "matched_courses", use the course names EXACTLY as given in the input — do not paraphrase or translate them.
- Suggest 3 to 5 job roles, ranked by match_percent descending.
- Keep every "reason" short (max 2 sentences) and grounded only in the provided courses/grades.
- Do NOT hardcode or default to any fixed list of technologies/certifications — infer
  "missing_skills", "recommended_certifications", and "recommended_projects" fresh for each
  role based on what real-world job postings for that role typically require versus what the
  transcript already covers.
- "recommended_certifications", "recommended_projects", and "salary_range_eur" must be
  plausible and genuinely relevant, but you may be estimating current market norms — phrase
  "reason" using hedged, non-absolute language ("typically requires", "is commonly expected
  to", "would likely benefit from") rather than stating these as guaranteed facts, since this
  is an AI estimate based on a transcript, not a guarantee.
- "recommended_learning_path" should have 3-5 short, concrete suggestions.
- Never include markdown, code fences, or any text outside the JSON object.
""".strip()

_MARKET_DEMAND_LEVELS = {"very high": "Very High", "high": "High", "medium": "Medium", "low": "Low"}


def _build_user_prompt(courses: list[dict]) -> str:
    lines = []
    for c in courses:
        grade = c.get("grade") or "no grade recorded"
        credits = c.get("credits")
        credit_str = f", {credits} ECTS" if credits else ""
        lines.append(f"- {c.get('course_name') or 'Unknown course'} | Grade: {grade}{credit_str}")
    return "Student's completed courses:\n" + "\n".join(lines)


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if not match:
            match = re.search(r"(\{.*\})", raw, re.DOTALL)
        if not match:
            raise ValueError("Gemini-Antwort enthält kein valides JSON.")
        return json.loads(match.group(1))


def _clean_str_list(value, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def _to_int(value, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, round(float(value))))
    except (TypeError, ValueError):
        return lo


def _normalize_market_demand(value) -> str:
    return _MARKET_DEMAND_LEVELS.get(str(value or "").strip().lower(), "Medium")


def _validate_skill(raw: dict) -> dict:
    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError("Skill ohne Namen in der Gemini-Antwort.")
    return {
        "name": name,
        "score": _to_int(raw.get("score", 0), 0, 5),
        "percent": _to_int(raw.get("percent", 0), 0, 100),
        "reason": str(raw.get("reason") or "").strip() or "No specific reasoning provided.",
        "matched_courses": _clean_str_list(raw.get("matched_courses")),
    }


def _validate_role(raw: dict) -> dict:
    title = str(raw.get("title", "")).strip()
    if not title:
        raise ValueError("Rolle ohne Titel in der Gemini-Antwort.")
    return {
        "title": title,
        "match_percent": _to_int(raw.get("match_percent", 0), 0, 100),
        "reason": str(raw.get("reason") or "").strip() or "Based on your overall academic profile.",
        "missing_skills": _clean_str_list(raw.get("missing_skills"), limit=8),
        "recommended_certifications": _clean_str_list(raw.get("recommended_certifications"), limit=4),
        "recommended_projects": _clean_str_list(raw.get("recommended_projects"), limit=3),
        "market_demand": _normalize_market_demand(raw.get("market_demand")),
        "salary_range_eur": str(raw.get("salary_range_eur") or "").strip(),
    }


def _enrich_matched_courses(skills: list[dict], courses: list[dict]) -> list[dict]:
    """Replaces each skill's plain course-name strings with {course_name, grade} pairs,
    looking the grade up from the real stored Grade rows — never trusting Gemini to recall
    grades accurately on its own."""
    grade_by_name: dict[str, tuple[str, str | None]] = {}
    for c in courses:
        name = (c.get("course_name") or "").strip()
        if name:
            grade_by_name.setdefault(name.lower(), (name, c.get("grade")))

    for skill in skills:
        enriched = []
        for course_name in skill["matched_courses"]:
            match = grade_by_name.get(course_name.strip().lower())
            if match:
                enriched.append({"course_name": match[0], "grade": match[1]})
            else:
                enriched.append({"course_name": course_name, "grade": None})
        skill["matched_courses"] = enriched
    return skills


def _validate_response(data: dict, courses: list[dict]) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Gemini-Antwort ist kein JSON-Objekt.")

    skills_raw = data.get("skills")
    if not isinstance(skills_raw, list) or not skills_raw:
        raise ValueError("Gemini-Antwort enthält keine 'skills'-Liste.")

    skills: list[dict] = []
    seen_names: set[str] = set()
    for s in skills_raw:
        if not isinstance(s, dict):
            continue
        try:
            validated = _validate_skill(s)
        except ValueError:
            continue
        key = validated["name"].lower()
        if key in seen_names:
            continue
        skills.append(validated)
        seen_names.add(key)

    if not skills:
        raise ValueError("Keine gültigen Skills in der Gemini-Antwort.")
    skills.sort(key=lambda s: s["percent"], reverse=True)
    skills = _enrich_matched_courses(skills, courses)

    roles_raw = data.get("roles")
    if not isinstance(roles_raw, list) or not roles_raw:
        raise ValueError("Gemini-Antwort enthält keine 'roles'-Liste.")
    roles = [_validate_role(r) for r in roles_raw if isinstance(r, dict)]
    if not roles:
        raise ValueError("Keine gültigen Rollen in der Gemini-Antwort.")
    roles.sort(key=lambda r: r["match_percent"], reverse=True)

    return {
        "has_data": True,
        "source": "ai",
        "summary": str(data.get("summary") or "").strip() or "No summary available.",
        "confidence_percent": _to_int(data.get("confidence_percent", 0), 0, 100),
        "job_fit_percent": _to_int(data.get("job_fit_percent", 0), 0, 100),
        "skills": skills,
        "roles": roles,
        "strengths": _clean_str_list(data.get("strengths")),
        "weak_areas": _clean_str_list(data.get("weak_areas")),
        "recommended_learning_path": _clean_str_list(data.get("recommended_learning_path")),
    }


def empty_analysis() -> dict:
    """Response shape for when the student has no stored grades yet (no Gemini call needed)."""
    return {
        "has_data": False,
        "source": "ai",
        "summary": "",
        "confidence_percent": 0,
        "job_fit_percent": 0,
        "skills": [],
        "roles": [],
        "strengths": [],
        "weak_areas": [],
        "recommended_learning_path": [],
    }


async def get_ai_career_analysis(courses: list[dict]) -> dict:
    """Runs the Gemini-based career analysis for a list of {course_name, grade, credits} dicts.

    Raises:
        RuntimeError: if Gemini fails or returns an unparsable/invalid response.
    """
    user_prompt = _build_user_prompt(courses)

    try:
        response = await _client.aio.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        raw = response.text or ""
    except Exception as exc:
        logger.error("Gemini-Anfrage (Career AI) fehlgeschlagen: %s", exc)
        raise RuntimeError("Gemini career analysis request failed.") from exc

    try:
        data = _extract_json(raw)
        return _validate_response(data, courses)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Career-AI-Antwort ungültig: %s\nRaw: %s", exc, raw[:500])
        raise RuntimeError("Gemini returned an invalid career analysis.") from exc
