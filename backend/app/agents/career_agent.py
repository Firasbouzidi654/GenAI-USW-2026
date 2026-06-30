"""CareerAgent — analysiert das akademische Profil und empfiehlt passende Berufsfelder.

Nutzt LangChain 1.x `create_agent` für konversationelle Karriereberatung und
`with_structured_output` für die strukturierte Karriere-Analyse-API.
"""

from __future__ import annotations

import json
import logging
import re

from langgraph.prebuilt import create_react_agent as create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import extract_text_output, get_llm, run_agent_with_model_fallback, run_with_model_fallback
from app.models.grade import Grade
from app.services.moodle_context_service import get_moodle_grades_context, get_moodle_courses_context

logger = logging.getLogger(__name__)

# ── Pydantic-Schemas für Structured Output ────────────────────────────────────

class _SkillSchema(BaseModel):
    name: str
    score: int = Field(ge=0, le=5)
    percent: int = Field(ge=0, le=100)
    reason: str
    matched_courses: list[str] = Field(default_factory=list)


class _RoleSchema(BaseModel):
    title: str
    match_percent: int = Field(ge=0, le=100)
    reason: str
    missing_skills: list[str] = Field(default_factory=list)
    recommended_certifications: list[str] = Field(default_factory=list)
    recommended_projects: list[str] = Field(default_factory=list)
    market_demand: str = "Medium"
    salary_range_eur: str = ""


class _CareerAnalysisSchema(BaseModel):
    summary: str
    confidence_percent: int = Field(ge=0, le=100)
    job_fit_percent: int = Field(ge=0, le=100)
    skills: list[_SkillSchema]
    roles: list[_RoleSchema]
    strengths: list[str]
    weak_areas: list[str]
    recommended_learning_path: list[str]


# ── System-Prompts ────────────────────────────────────────────────────────────

_ANALYSIS_SYSTEM_PROMPT = """
Du bist ein KI-Karriereberater, der das Notenblatt eines Studierenden analysiert.

Analysiere frei — kein festes Skill-Set, nur was die tatsächlichen Kurse belegen.
Empfehle 3–5 passende Berufsfelder mit konkreten Lernpfaden.

Skills (5–10 Einträge):
- Nur Skills die wirklich durch Kurse belegt sind
- Fehlende wichtige Skills mit score=0 als Gap markieren
- matched_courses: exakte Kursnamen aus dem Input

Rollen:
- Realistische Job-Titel aus dem deutschen Markt
- missing_skills: konkrete Tools/Technologien (nicht vage)
- recommended_certifications: echte, bekannte Zertifikate
- salary_range_eur: Format '€55.000 – €75.000 pro Jahr'
- market_demand: 'Very High' | 'High' | 'Medium' | 'Low'
""".strip()

_AGENT_SYSTEM_PROMPT = """
Du bist ein Karriere-Agent für Studierende. Du analysierst ihr akademisches Profil
und gibst personalisierte Karriereempfehlungen.

Du hast Zugriff auf:
- LSF-Noten (get_academic_transcript, get_strong_subjects, get_weak_subjects)
- Moodle-Noten aus laufenden Kursen (get_moodle_grades) — ergänzen das LSF-Notenblatt
- Belegte Moodle-Kurse (get_moodle_courses)

Nutze alle verfügbaren Datenquellen, dann analysiere das Profil.
Antworte auf Deutsch mit konkreten, motivierenden Empfehlungen.
""".strip()

_ANALYSIS_JSON_INSTRUCTIONS = """
Antworte ausschliesslich mit einem validen JSON-Objekt ohne Markdown.
Das JSON muss exakt diese Keys enthalten:
- summary: string
- confidence_percent: integer 0-100
- job_fit_percent: integer 0-100
- skills: array of objects with name, score, percent, reason, matched_courses
- roles: array of objects with title, match_percent, reason, missing_skills,
  recommended_certifications, recommended_projects, market_demand, salary_range_eur
- strengths: array of strings
- weak_areas: array of strings
- recommended_learning_path: array of strings
matched_courses muss eine Liste von Kursnamen als Strings sein.
""".strip()


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _enrich_matched_courses(skills: list[dict], courses: list[dict]) -> list[dict]:
    """Reichert plain course-name Strings mit {course_name, grade}-Dicts an."""
    grade_by_name = {
        (c.get("course_name") or "").strip().lower(): (c.get("course_name"), c.get("grade"))
        for c in courses
        if c.get("course_name")
    }
    for skill in skills:
        enriched = []
        for course_name in skill.get("matched_courses", []):
            match = grade_by_name.get(course_name.strip().lower())
            if match:
                enriched.append({"course_name": match[0], "grade": match[1]})
            else:
                enriched.append({"course_name": course_name, "grade": None})
        skill["matched_courses"] = enriched
    return skills


def empty_analysis() -> dict:
    """Leere Analyse wenn noch keine Noten vorhanden sind."""
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


def _response_to_text(response) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return ""


def _extract_json_object(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text or ""):
        try:
            value, _end = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "summary" in value and "skills" in value and "roles" in value:
            return value
    return None


def _analysis_from_json_text(text: str) -> _CareerAnalysisSchema | None:
    payload = _extract_json_object(text)
    if not payload:
        return None
    try:
        return _CareerAnalysisSchema.model_validate(payload)
    except Exception as exc:
        logger.warning("CareerAgent JSON-Fallback konnte nicht validiert werden: %s", exc)
        return None


# ── Agent-Factory ─────────────────────────────────────────────────────────────

def create_career_agent(db: AsyncSession, llm=None):
    """Erstellt einen CareerAgent für konversationelle Karriereberatung."""

    @tool
    async def get_academic_transcript() -> str:
        """Holt das vollständige Notenblatt des Studierenden.
        Enthält Kursnamen, Noten (1.0–5.0), ECTS und Semester."""
        try:
            result = await db.execute(select(Grade))
            grades = result.scalars().all()
            if not grades:
                return "Keine Noten vorhanden. Der Studierende hat noch keine Kurse eingetragen."

            lines = []
            for g in grades:
                grade = g.grade or "keine Note"
                credits = f", {g.credits} ECTS" if g.credits else ""
                semester = f" ({g.semester})" if g.semester else ""
                lines.append(f"- {g.course_name} | Note: {grade}{credits}{semester}")
            return "Notenblatt:\n" + "\n".join(lines)
        except Exception as exc:
            logger.warning("Notenblatt-Abfrage fehlgeschlagen: %s", exc)
            return "Notenblatt konnte nicht abgerufen werden."

    @tool
    async def get_strong_subjects() -> str:
        """Identifiziert Stärken: Fächer mit sehr guten Noten (≤2.0)."""
        try:
            result = await db.execute(select(Grade))
            grades = result.scalars().all()
            strong = []
            for g in grades:
                if g.grade:
                    try:
                        if float(g.grade.replace(",", ".")) <= 2.0:
                            strong.append({"course": g.course_name, "grade": g.grade, "credits": g.credits})
                    except ValueError:
                        pass
            return json.dumps(strong, ensure_ascii=False) if strong else "Keine besonders starken Fächer (≤2.0) gefunden."
        except Exception as exc:
            logger.warning("Stärken-Abfrage fehlgeschlagen: %s", exc)
            return "Stärken konnten nicht ermittelt werden."

    @tool
    async def get_weak_subjects() -> str:
        """Identifiziert Schwächen: Fächer mit schlechten Noten (≥4.0) als Verbesserungsbedarf."""
        try:
            result = await db.execute(select(Grade))
            grades = result.scalars().all()
            weak = []
            for g in grades:
                if g.grade:
                    try:
                        if float(g.grade.replace(",", ".")) >= 4.0:
                            weak.append({"course": g.course_name, "grade": g.grade, "credits": g.credits})
                    except ValueError:
                        pass
            return json.dumps(weak, ensure_ascii=False) if weak else "Keine Fächer mit schlechten Noten (≥4.0) gefunden."
        except Exception as exc:
            logger.warning("Schwächen-Abfrage fehlgeschlagen: %s", exc)
            return "Schwächen konnten nicht ermittelt werden."

    @tool
    async def get_moodle_grades(course_name: str = "") -> str:
        """Holt Moodle-Noten aus laufenden Kursen. Ohne Kursname: alle Kurse.
        Mit Kursname: nur dieser Kurs.

        Args:
            course_name: Kursname oder leer für alle Kurse.
        """
        return await get_moodle_grades_context(course_name or None)

    @tool
    async def get_moodle_courses() -> str:
        """Listet alle belegten Moodle-Kurse des Studierenden."""
        return await get_moodle_courses_context()

    llm = llm or get_llm(temperature=0.2)
    return create_agent(
        model=llm,
        tools=[get_academic_transcript, get_strong_subjects, get_weak_subjects,
               get_moodle_grades, get_moodle_courses],
        prompt=_AGENT_SYSTEM_PROMPT,
    )


# ── Öffentliche API ───────────────────────────────────────────────────────────

async def get_ai_career_analysis(
    courses: list[dict],
    cv_text: str | None = None,
    quiz_topics: list[dict] | None = None,
) -> dict:
    """Strukturierte Karriere-Analyse via LangChain Structured Output.

    Raises:
        RuntimeError: Bei LLM-Fehlern.
    """
    lines = []
    for c in courses:
        grade = c.get("grade") or "keine Note"
        credits = c.get("credits")
        credit_str = f", {credits} ECTS" if credits else ""
        lines.append(f"- {c.get('course_name') or 'Unbekannter Kurs'} | Note: {grade}{credit_str}")

    user_prompt = "Notenblatt des Studierenden:\n" + "\n".join(lines)

    if cv_text:
        user_prompt += f"\n\nLebenslauf:\n{cv_text}"

    if quiz_topics:
        quiz_lines = [
            f"- {t.get('topic')}: {t.get('score')}% (Level: {t.get('level')})"
            for t in quiz_topics
            if t.get("topic")
        ]
        if quiz_lines:
            user_prompt += "\n\nQuiz-Ergebnisse:\n" + "\n".join(quiz_lines)

    async def _invoke(llm):
        structured_llm = llm.with_structured_output(_CareerAnalysisSchema)
        return await structured_llm.ainvoke([
            SystemMessage(content=_ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])

    try:
        result: _CareerAnalysisSchema = await run_with_model_fallback(_invoke, temperature=0.2)
    except Exception as exc:
        result = _analysis_from_json_text(str(exc))
        if result is None:
            async def _invoke_json(llm):
                return await llm.ainvoke([
                    SystemMessage(content=f"{_ANALYSIS_SYSTEM_PROMPT}\n\n{_ANALYSIS_JSON_INSTRUCTIONS}"),
                    HumanMessage(content=user_prompt),
                ])

            try:
                response = await run_with_model_fallback(_invoke_json, temperature=0.2)
                result = _analysis_from_json_text(_response_to_text(response))
            except Exception as json_exc:
                logger.error("CareerAgent JSON-Fallback fehlgeschlagen: %s", json_exc)
                result = None
        if result is None:
            logger.error("CareerAgent Analyse fehlgeschlagen: %s", exc)
            raise RuntimeError("KI-Karriereanalyse fehlgeschlagen.") from exc
        logger.warning("CareerAgent structured output failed; using parsed JSON fallback")

    skills_raw = [s.model_dump() for s in result.skills]
    enriched_skills = _enrich_matched_courses(skills_raw, courses)

    roles_sorted = sorted(
        [r.model_dump() for r in result.roles],
        key=lambda r: r["match_percent"],
        reverse=True,
    )

    return {
        "has_data": True,
        "source": "ai",
        "summary": result.summary,
        "confidence_percent": result.confidence_percent,
        "job_fit_percent": result.job_fit_percent,
        "skills": sorted(enriched_skills, key=lambda s: s["percent"], reverse=True),
        "roles": roles_sorted,
        "strengths": result.strengths,
        "weak_areas": result.weak_areas,
        "recommended_learning_path": result.recommended_learning_path,
    }


async def run_career_agent(message: str, db: AsyncSession) -> str:
    """Führt den CareerAgent für konversationelle Karriereberatung aus."""
    try:
        result = await run_agent_with_model_fallback(
            lambda llm: create_career_agent(db, llm=llm),
            {"messages": [HumanMessage(content=message)]},
            temperature=0.2,
        )
        return extract_text_output(result) or "Die Karriereanalyse konnte nicht abgeschlossen werden."
    except Exception as exc:
        logger.error("CareerAgent fehlgeschlagen: %s", exc)
        return "Der Karriere-Agent ist momentan nicht erreichbar. Bitte später erneut versuchen."
