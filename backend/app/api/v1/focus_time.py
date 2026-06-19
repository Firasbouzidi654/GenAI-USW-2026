from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.focus_session import FocusSession

router = APIRouter()


class FocusSessionIn(BaseModel):
    date: date
    focus_minutes: float = Field(ge=0.1, le=240)
    break_minutes: float = Field(ge=0.1, le=120)
    completed_cycles: int = Field(ge=1, le=50)
    selected_theme: str = Field(min_length=1, max_length=40)


class FocusSessionOut(BaseModel):
    id: int
    date: date
    focus_minutes: float
    break_minutes: float
    completed_cycles: int
    total_focus_time: float
    selected_theme: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FocusSummaryOut(BaseModel):
    date: date
    sessions: int
    completed_cycles: int
    total_focus_time: float
    themes: list[str]


@router.post("/focus-time/sessions", response_model=FocusSessionOut, status_code=201)
async def create_focus_session(body: FocusSessionIn, db: AsyncSession = Depends(get_db)):
    try:
        session = FocusSession(
            date=body.date,
            focus_minutes=body.focus_minutes,
            break_minutes=body.break_minutes,
            completed_cycles=body.completed_cycles,
            total_focus_time=body.focus_minutes * body.completed_cycles,
            selected_theme=body.selected_theme,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.get("/focus-time/today", response_model=FocusSummaryOut)
async def get_focus_today(
    day: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    target_day = day or date.today()
    try:
        result = await db.execute(
            select(
                func.count(FocusSession.id),
                func.coalesce(func.sum(FocusSession.completed_cycles), 0),
                func.coalesce(func.sum(FocusSession.total_focus_time), 0),
            ).where(FocusSession.date == target_day)
        )
        sessions, completed_cycles, total_focus_time = result.one()

        theme_result = await db.execute(
            select(FocusSession.selected_theme)
            .where(FocusSession.date == target_day)
            .distinct()
            .order_by(FocusSession.selected_theme)
        )
        return {
            "date": target_day,
            "sessions": sessions,
            "completed_cycles": completed_cycles,
            "total_focus_time": total_focus_time,
            "themes": list(theme_result.scalars().all()),
        }
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")
