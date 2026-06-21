import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.career_agent import empty_analysis, get_ai_career_analysis
from app.api.v1.tutor import _compute_topic_mastery
from app.core.config import settings
from app.core.database import get_db
from app.models.grade import Grade
from app.models.resume import Resume
from app.services.job_links import build_job_links
from app.services.job_service import active_source, search_jobs

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_USER = "local"


async def _get_cv_text(db: AsyncSession, user_id: str = _DEFAULT_USER) -> str | None:
    result = await db.execute(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc())
    )
    cv = result.scalars().first()
    return cv.content if cv else None


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
    quiz_topics: list[QuizTopicOut] = []


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
        analysis = await get_ai_career_analysis(courses, cv_text=cv_text, quiz_topics=quiz_topics)
    except RuntimeError as exc:
        logger.error("Career AI analysis failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Die KI-Karriereanalyse ist momentan nicht verfügbar. Bitte später erneut versuchen.",
        )

    # Datenbasis (was floss in die Analyse ein?)
    avg = round(sum(t["score"] for t in quiz_topics) / len(quiz_topics)) if quiz_topics else 0
    analysis["data_sources"] = {
        "grades_count": len(courses),
        "has_cv": bool(cv_text),
        "quiz_topics_count": len(quiz_topics),
        "quiz_avg_score": avg,
        "quiz_topics": [
            {"topic": t["topic"], "score": t["score"], "level": t["level"]} for t in quiz_topics
        ],
    }

    # Vorgefilterte Such-Links (LinkedIn/StepStone/Indeed) pro empfohlener Rolle
    roles = analysis.get("roles", [])
    for role in roles:
        role["search_links"] = build_job_links(
            role["title"], location=settings.job_location, experience="entry"
        )

    # Echte Stellenanzeigen — Suche NUR mit stark belegten Skills (≥90 %)
    analysis["job_source"] = active_source()
    strong_skills = [s["name"] for s in analysis.get("skills", []) if s.get("percent", 0) >= 90]
    if strong_skills:
        analysis["jobs"] = await search_jobs(strong_skills[:4], limit=8)
    elif roles:
        # Kein Skill ≥90 % → ersatzweise nach der besten Rolle suchen
        analysis["jobs"] = await search_jobs([roles[0]["title"]], limit=8)

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
