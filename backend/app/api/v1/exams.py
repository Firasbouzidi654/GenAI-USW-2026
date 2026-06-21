"""Prüfungen-Endpunkt — read-only. Prüfungstermine stammen aus dem LSF-Mock (via Sync)."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.exam import Exam

router = APIRouter()


class ExamResponse(BaseModel):
    id: int
    subject: str
    exam_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/exams", response_model=list[ExamResponse])
async def get_exams(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Exam).order_by(Exam.exam_date))
        return result.scalars().all()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")
