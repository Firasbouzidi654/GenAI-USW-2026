"""Noten-Endpunkt — read-only. Die Daten stammen aus dem LSF-Mock (via Sync)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.grade import Grade

router = APIRouter()


class CourseResult(BaseModel):
    courseName: str
    semester: str | None = None
    grade: str | None = None
    credits: int | None = None


class GradesResponse(BaseModel):
    studentName: str | None = None
    totalCredits: int | None = None
    courses: list[CourseResult]


@router.get("/grades", response_model=GradesResponse)
async def get_grades(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Grade).order_by(Grade.semester, Grade.course_name))
        rows = result.scalars().all()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    student_name = next((r.student_name for r in rows if r.student_name), None)
    total_credits = sum(r.credits for r in rows if r.credits) or None
    return GradesResponse(
        studentName=student_name,
        totalCredits=total_credits,
        courses=[
            CourseResult(courseName=r.course_name, semester=r.semester, grade=r.grade, credits=r.credits)
            for r in rows
        ],
    )
