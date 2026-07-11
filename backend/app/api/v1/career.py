import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.career_agent import empty_analysis, get_ai_career_analysis
from app.agents.evaluator_agent import _match_module
from app.api.v1.tutor import _compute_topic_mastery
from app.core.config import settings
from app.core.database import get_db
from app.models.curriculum import CurriculumModule
from app.models.grade import Grade
from app.models.resume import Resume
from app.services.job_links import build_job_links
from app.services.job_service import active_source, search_jobs

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_USER = "local"

# Schwellen für "starke" Bereiche, die die Jobsuche speisen
_STRONG_QUIZ_PERCENT = 90      # Quiz gilt erst ab 90 % als belegte Stärke
_STRONG_GRADE_MAX = 1.5        # Note ≤ 1,5 (sehr gut) gilt als Stärke


def _parse_grade(grade: str | None) -> float | None:
    """Wandelt eine deutsche Note ('1,0' / '1.3') in float um. None bei Nicht-Noten."""
    if not grade:
        return None
    try:
        return float(str(grade).strip().replace(",", "."))
    except (ValueError, TypeError):
        return None


async def _get_cv_text(db: AsyncSession, user_id: str = _DEFAULT_USER) -> str | None:
    result = await db.execute(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc())
    )
    cv = result.scalars().first()
    return cv.content if cv else None


async def _build_job_keywords(
    db: AsyncSession, quiz_topics: list[dict], courses: list[dict]
) -> tuple[list[str], list[str]]:
    """Leitet Job-Suchbegriffe aus den STARKEN Bereichen ab.

    Stark = Quiz-Thema ≥ 90 % ODER Modul-Note ≤ 1,5. Für jedes starke Modul werden
    die im Modulhandbuch hinterlegten KOMPETENZEN/Technologien als Suchbegriffe genutzt
    (z.B. Webtechnologien → 'Java Spring Boot', 'Vue.js', 'Postgresql').

    Returns (keywords, strong_module_names).
    """
    # Starke Module sammeln — quiz-belegte zuerst (höhere Priorität), dann gute Noten
    strong_names: list[str] = []
    for t in sorted(quiz_topics, key=lambda x: x.get("score", 0), reverse=True):
        if t.get("score", 0) >= _STRONG_QUIZ_PERCENT and t.get("topic"):
            strong_names.append(t["topic"])
    graded = [(c, _parse_grade(c.get("grade"))) for c in courses]
    for c, g in sorted((x for x in graded if x[1] is not None), key=lambda x: x[1]):
        if g <= _STRONG_GRADE_MAX and c.get("course_name"):
            strong_names.append(c["course_name"])

    # Duplikate (gleicher Modulname aus Quiz + Note) entfernen, Reihenfolge erhalten
    seen_mod: set[str] = set()
    unique_names = [n for n in strong_names if not (n.lower() in seen_mod or seen_mod.add(n.lower()))]
    if not unique_names:
        return [], []

    try:
        modules = (await db.execute(select(CurriculumModule))).scalars().all()
    except Exception:
        modules = []

    # Pro starkem Modul die Kompetenzen sammeln (Fallback: Modulname)
    per_module: list[list[str]] = []
    matched_modules: list[str] = []
    for name in unique_names:
        m = _match_module(modules, name) if modules else None
        if m and m.competencies:
            matched_modules.append(m.name)
            per_module.append([c.strip() for c in m.competencies if c and c.strip()])
        else:
            per_module.append([name.strip()])

    # Round-Robin über die Module, damit die (begrenzte) Jobsuche MEHRERE starke
    # Bereiche abdeckt statt nur das erste Modul.
    from itertools import zip_longest
    seen_kw: set[str] = set()
    cleaned: list[str] = []
    for group in zip_longest(*per_module):
        for k in group:
            if not k:
                continue
            kl = k.lower()
            if kl not in seen_kw:
                seen_kw.add(kl)
                cleaned.append(k)
    return cleaned, matched_modules


class MatchedCourseOut(BaseModel):
    course_name: str
    grade: str | None = None


class SkillOut(BaseModel):
    name: str
    score: int
    percent: int
    reason: str
    matched_courses: list[MatchedCourseOut]


class JobLinkOut(BaseModel):
    portal: str
    url: str


class RoleOut(BaseModel):
    title: str
    match_percent: int
    reason: str
    missing_skills: list[str] = []
    recommended_certifications: list[str] = []
    recommended_projects: list[str] = []
    market_demand: str = "Medium"
    salary_range_eur: str = ""
    search_links: list[JobLinkOut] = []


class JobOut(BaseModel):
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    salary: str | None = None
    remote: bool | None = None
    description: str = ""
    source: str = ""


class QuizTopicOut(BaseModel):
    topic: str
    score: int
    level: str


class DataSourcesOut(BaseModel):
    grades_count: int = 0
    has_cv: bool = False
    quiz_topics_count: int = 0
    quiz_avg_score: int = 0
    quiz_topics: list[QuizTopicOut] = []      # nur belegte Stärken (≥ 90 %)
    job_keywords: list[str] = []              # Suchbegriffe, die die Jobsuche speisen
    strong_modules: list[str] = []            # starke Module (Quiz ≥90 % oder Note ≤1,5)


class CareerAnalysisOut(BaseModel):
    has_data: bool
    source: str = "ai"
    summary: str = ""
    confidence_percent: int = 0
    job_fit_percent: int
    skills: list[SkillOut]
    roles: list[RoleOut]
    strengths: list[str] = []
    weak_areas: list[str] = []
    recommended_learning_path: list[str] = []
    jobs: list[JobOut] = []
    job_source: str = ""
    data_sources: DataSourcesOut = DataSourcesOut()


@router.get("/career/analysis", response_model=CareerAnalysisOut)
async def get_career_analysis(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Grade))
        rows = result.scalars().all()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    courses = [
        {"course_name": r.course_name, "grade": r.grade, "credits": r.credits}
        for r in rows
    ]

    cv_text = await _get_cv_text(db)

    # Quiz-Beherrschung pro Thema (fließt in die Analyse ein + macht sichtbar, was zählt)
    try:
        quiz_topics = await _compute_topic_mastery(db)
    except Exception:
        quiz_topics = []

    if not courses and not cv_text and not quiz_topics:
        return empty_analysis()

    try:
        analysis = await get_ai_career_analysis(
            courses, cv_text=cv_text, quiz_topics=quiz_topics,
            study_program=settings.study_program,
        )
    except RuntimeError as exc:
        logger.error("Career AI analysis failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Die KI-Karriereanalyse ist momentan nicht verfügbar. Bitte später erneut versuchen.",
        )

    # Job-Suchbegriffe aus den STARKEN Modulen (Quiz ≥90 % / Note ≤1,5) → deren
    # Curriculum-Kompetenzen/Technologien (z.B. Webtech → Java Spring Boot, Vue.js).
    job_keywords, strong_modules = await _build_job_keywords(db, quiz_topics, courses)

    # Datenbasis (was floss in die Analyse ein?) — als "bestätigt" nur Themen ≥90 %
    avg = round(sum(t["score"] for t in quiz_topics) / len(quiz_topics)) if quiz_topics else 0
    confirmed_topics = [t for t in quiz_topics if t["score"] >= _STRONG_QUIZ_PERCENT]
    analysis["data_sources"] = {
        "grades_count": len(courses),
        "has_cv": bool(cv_text),
        "quiz_topics_count": len(quiz_topics),
        "quiz_avg_score": avg,
        "quiz_topics": [
            {"topic": t["topic"], "score": t["score"], "level": t["level"]} for t in confirmed_topics
        ],
        "job_keywords": job_keywords[:10],
        "strong_modules": strong_modules,
    }

    # Vorgefilterte Such-Links (LinkedIn/StepStone/Indeed) pro empfohlener Rolle
    roles = analysis.get("roles", [])
    for role in roles:
        role["search_links"] = build_job_links(
            role["title"], location=settings.job_location, experience="entry"
        )

    # Echte Stellenanzeigen — primär nach den Technologien/Kompetenzen der starken Module.
    # Der Studiengang fließt als zusätzliches Stichwort ein (steht oft in Werkstudenten-Ausschreibungen).
    analysis["job_source"] = active_source()
    prog = settings.study_program
    if job_keywords:
        analysis["jobs"] = await search_jobs(job_keywords[:5], limit=8, study_program=prog)
    else:
        # Fallback: stark belegte KI-Skills (≥90 %), sonst beste Rolle
        strong_skills = [s["name"] for s in analysis.get("skills", []) if s.get("percent", 0) >= 90]
        if strong_skills:
            analysis["jobs"] = await search_jobs(strong_skills[:4], limit=8, study_program=prog)
        elif roles:
            analysis["jobs"] = await search_jobs([roles[0]["title"]], limit=8, study_program=prog)

    return analysis


class CvStatusOut(BaseModel):
    has_cv: bool
    filename: str | None = None


@router.get("/career/cv", response_model=CvStatusOut)
async def get_cv_status(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(Resume).where(Resume.user_id == _DEFAULT_USER).order_by(Resume.uploaded_at.desc())
        )
        cv = result.scalars().first()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")
    return CvStatusOut(has_cv=cv is not None, filename=cv.filename if cv else None)


@router.post("/career/cv", response_model=CvStatusOut)
async def upload_cv(file: UploadFile, db: AsyncSession = Depends(get_db)):
    """Lädt einen Lebenslauf (PDF) hoch, extrahiert den Text und speichert ihn.

    Der Text fließt anschließend in die KI-Karriereanalyse ein.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt.")

    contents = await file.read()

    # Text aus dem PDF extrahieren
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(contents))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as exc:
        logger.warning("CV-PDF konnte nicht gelesen werden: %s", exc)
        raise HTTPException(status_code=422, detail="PDF konnte nicht gelesen werden.")

    if not text:
        raise HTTPException(
            status_code=422,
            detail="Im PDF wurde kein Text gefunden (evtl. ein gescanntes Bild?).",
        )

    filename = file.filename
    try:
        # Singleton: alten CV ersetzen
        await db.execute(delete(Resume).where(Resume.user_id == _DEFAULT_USER))
        db.add(Resume(user_id=_DEFAULT_USER, filename=filename, content=text))
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="CV konnte nicht gespeichert werden.")

    return CvStatusOut(has_cv=True, filename=filename)


@router.delete("/career/cv", status_code=204)
async def delete_cv(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(delete(Resume).where(Resume.user_id == _DEFAULT_USER))
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="CV konnte nicht gelöscht werden.")
