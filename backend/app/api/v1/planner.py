from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.academic_event import AcademicEvent
from app.services.planner_service import get_event_priority

router = APIRouter()

VALID_TYPES = {"EXAM", "ASSIGNMENT", "PRESENTATION"}


class AcademicEventIn(BaseModel):
    title: str
    course_name: str
    type: str
    date: date
    description: str | None = None


class AcademicEventOut(BaseModel):
    id: int
    title: str
    course_name: str
    type: str
    date: date
    description: str | None
    created_at: datetime
    days_remaining: int
    priority: str

    model_config = {"from_attributes": True}


def _enrich(event: AcademicEvent) -> dict:
    p = get_event_priority(event.date)
    return {
        "id": event.id,
        "title": event.title,
        "course_name": event.course_name,
        "type": event.type,
        "date": event.date,
        "description": event.description,
        "created_at": event.created_at,
        **p,
    }


@router.post("/planner/events", response_model=AcademicEventOut, status_code=201)
async def create_event(body: AcademicEventIn, db: AsyncSession = Depends(get_db)):
    if body.type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {sorted(VALID_TYPES)}.")
    try:
        event = AcademicEvent(
            title=body.title.strip(),
            course_name=body.course_name.strip(),
            type=body.type,
            date=body.date,
            description=body.description,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return _enrich(event)
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.get("/planner/events", response_model=list[AcademicEventOut])
async def get_events(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(AcademicEvent).order_by(AcademicEvent.date))
        return [_enrich(e) for e in result.scalars().all()]
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.get("/planner/events/upcoming", response_model=list[AcademicEventOut])
async def get_upcoming_events(db: AsyncSession = Depends(get_db)):
    try:
        today = date.today()
        result = await db.execute(
            select(AcademicEvent)
            .where(AcademicEvent.date >= today)
            .order_by(AcademicEvent.date)
        )
        return [_enrich(e) for e in result.scalars().all()]
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.delete("/planner/events/{event_id}", status_code=204)
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(AcademicEvent).where(AcademicEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if event is None:
            raise HTTPException(status_code=404, detail="Event nicht gefunden.")
        await db.delete(event)
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")
