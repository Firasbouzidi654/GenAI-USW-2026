"""CareerAgent — analysiert das akademische Profil und empfiehlt passende Berufsfelder.

Nutzt LangChain 1.x `create_agent` für konversationelle Karriereberatung und
`with_structured_output` für die strukturierte Karriere-Analyse-API.
"""

from __future__ import annotations

import json
import logging

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import extract_text_output, get_llm
from app.models.grade import Grade

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
Du bist ein KI-Karriereberater für einen STUDIERENDEN, der NEBEN dem Studium eine
Werkstudentenstelle (oder ein Praktikum) sucht — KEINE Vollzeit-/Senior-Stelle.

Analysiere frei — kein festes Skill-Set, nur was die tatsächlichen Kurse belegen.
Empfehle 3–5 passende WERKSTUDENTEN-Stellen mit konkreten Lernpfaden.

Skills (5–10 Einträge):
- Nur Skills die wirklich durch Kurse belegt sind
- Fehlende wichtige Skills mit score=0 als Gap markieren
- matched_courses: exakte Kursnamen aus dem Input

Rollen (WICHTIG — es sind Werkstudenten-Positionen, keine Vollzeitstellen):
- title: als Werkstudenten-Stelle formulieren, z.B. 'Werkstudent:in Data Analytics',
  'Werkstudent:in Business Intelligence', 'Werkstudent:in Softwareentwicklung',
  'Praktikant:in Controlling' — NICHT 'Business Analyst' oder 'IT-Consultant' als Vollzeit.
- missing_skills: konkrete Tools/Technologien (nicht vage)
- recommended_certifications: echte, bekannte Zertifikate (für Studierende erreichbar)
- salary_range_eur: typische WERKSTUDENTEN-Vergütung in Deutschland, Format
  '€15 – €20 pro Stunde' (NICHT Jahresgehalt einer Vollzeitstelle).
- market_demand: 'Very High' | 'High' | 'Medium' | 'Low'
""".strip()

_AGENT_SYSTEM_PROMPT = """
Du bist ein Karriere-Agent für Studierende. Du analysierst ihr akademisches Profil
und gibst personalisierte Karriereempfehlungen.

Nutze deine Tools, um Daten zu sammeln, dann analysiere das Profil.
Antworte auf Deutsch mit konkreten, motivierenden Empfehlungen.
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


# ── Agent-Factory ─────────────────────────────────────────────────────────────

def create_career_agent(db: AsyncSession):
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

    llm = get_llm(temperature=0.2)
    return create_agent(
        model=llm,
        tools=[get_academic_transcript, get_strong_subjects, get_weak_subjects],
        system_prompt=_AGENT_SYSTEM_PROMPT,
    )


# ── Öffentliche API ───────────────────────────────────────────────────────────

async def get_ai_career_analysis(
    courses: list[dict],
    cv_text: str | None = None,
    quiz_topics: list[dict] | None = None,
) -> dict:
    """Strukturierte Karriere-Analyse via LangChain Structured Output.

    Args:
        courses: Liste der Module mit Note/ECTS.
        cv_text: Optionaler Lebenslauf-Text (aus hochgeladenem PDF). Fließt zusätzlich
            in die Analyse ein, um Erfahrungen/Projekte/Skills jenseits der Noten zu erfassen.
        quiz_topics: Optionale Quiz-Beherrschung pro Thema (score 0–100). Belegt praktisch
            nachgewiesenes Können (hoher Score = bestätigter Skill, niedriger Score = Lücke).

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

    if quiz_topics:
        quiz_lines = [
            f"- {t.get('topic')}: {t.get('score')}/100 "
            f"({t.get('correct')}/{t.get('total')} Fragen richtig)"
            for t in quiz_topics
        ]
        user_prompt += (
            "\n\nQuiz-Leistung des Studierenden (praktisch nachgewiesene Themen-Beherrschung — "
            "hohe Werte bestätigen einen Skill, niedrige Werte sind echte Lücken; bewerte die "
            "betroffenen Skills entsprechend höher bzw. niedriger):\n" + "\n".join(quiz_lines)
        )

    if cv_text and cv_text.strip():
        # Auf eine sinnvolle Länge begrenzen, damit der Prompt nicht explodiert.
        snippet = cv_text.strip()[:6000]
        user_prompt += (
            "\n\nLebenslauf des Studierenden (zusätzlich berücksichtigen — "
            "Praktika, Projekte, Tools, Sprachen, Engagement):\n" + snippet
        )

    llm = get_llm(temperature=0.2)
    structured_llm = llm.with_structured_output(_CareerAnalysisSchema)

    try:
        result: _CareerAnalysisSchema = await structured_llm.ainvoke([
            SystemMessage(content=_ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
    except Exception as exc:
        logger.error("CareerAgent Analyse fehlgeschlagen: %s", exc)
        raise RuntimeError("KI-Karriereanalyse fehlgeschlagen.") from exc

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
    agent = create_career_agent(db)
    try:
        result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
        return extract_text_output(result) or "Die Karriereanalyse konnte nicht abgeschlossen werden."
    except Exception as exc:
        logger.error("CareerAgent fehlgeschlagen: %s", exc)
        return "Der Karriere-Agent ist momentan nicht erreichbar. Bitte später erneut versuchen."
