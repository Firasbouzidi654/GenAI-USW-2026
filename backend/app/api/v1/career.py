import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.grade import Grade
from app.services.career_ai_service import empty_analysis, get_ai_career_analysis

logger = logging.getLogger(__name__)

router = APIRouter()


class MatchedCourseOut(BaseModel):
    course_name: str
    grade: str | None = None


class SkillOut(BaseModel):
    name: str
    score: int
    percent: int
    reason: str
    matched_courses: list[MatchedCourseOut]


class RoleOut(BaseModel):
    title: str
    match_percent: int
    reason: str
    missing_skills: list[str] = []
    recommended_certifications: list[str] = []
    recommended_projects: list[str] = []
    market_demand: str = "Medium"
    salary_range_eur: str = ""


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

    if not courses:
        return empty_analysis()

    try:
        return await get_ai_career_analysis(courses)
    except RuntimeError as exc:
        logger.error("Career AI analysis failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="AI career analysis is currently unavailable. Please try again.",
        )
