from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.exam import Exam

router = APIRouter()


class ExamRequest(BaseModel):
    subject: str
    exam_date: date


class ExamResponse(BaseModel):
    id: int
    subject: str
    exam_date: date
    created_at: datetime


@router.get("/exams", response_model=list[ExamResponse])
async def get_exams(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Exam).order_by(Exam.exam_date))
        return result.scalars().all()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.post("/exams", response_model=ExamResponse, status_code=201)
async def create_exam(body: ExamRequest, db: AsyncSession = Depends(get_db)):
    try:
        exam = Exam(subject=body.subject, exam_date=body.exam_date)
        db.add(exam)
        await db.commit()
        await db.refresh(exam)
        return exam
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.delete("/exams/{exam_id}", status_code=204)
async def delete_exam(exam_id: int, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Exam).where(Exam.id == exam_id))
        exam = result.scalar_one_or_none()
        if exam is None:
            raise HTTPException(status_code=404, detail="Prüfung nicht gefunden.")
        await db.delete(exam)
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")