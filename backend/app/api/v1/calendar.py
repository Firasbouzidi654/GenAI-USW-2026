from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.calendar_event import CalendarEvent

router = APIRouter()


class CalendarEventIn(BaseModel):
    uid: str
    title: str
    start_time: datetime
    end_time: datetime
    location: str | None = None
    description: str | None = None


class CalendarEventsBatchIn(BaseModel):
    events: list[CalendarEventIn]


class CalendarEventOut(BaseModel):
    id: int
    uid: str
    title: str
    start_time: datetime
    end_time: datetime
    location: str | None
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/calendar/events", response_model=list[CalendarEventOut])
async def get_calendar_events(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(CalendarEvent).order_by(CalendarEvent.start_time)
        )
        return result.scalars().all()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.post("/calendar/events", response_model=dict, status_code=200)
async def upsert_calendar_events(
    body: CalendarEventsBatchIn, db: AsyncSession = Depends(get_db)
):
    if not body.events:
        raise HTTPException(status_code=422, detail="Keine Events übergeben.")
    try:
        rows = [
            {
                "uid": e.uid,
                "title": e.title,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "location": e.location,
                "description": e.description,
            }
            for e in body.events
        ]
        stmt = insert(CalendarEvent).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["uid"],
            set_={
                "title": stmt.excluded.title,
                "start_time": stmt.excluded.start_time,
                "end_time": stmt.excluded.end_time,
                "location": stmt.excluded.location,
                "description": stmt.excluded.description,
            },
        )
        await db.execute(stmt)
        await db.commit()
        return {"upserted": len(rows)}
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.delete("/calendar/events", status_code=204)
async def delete_all_calendar_events(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(delete(CalendarEvent))
        await db.commit()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.delete("/calendar/events/{event_id}", status_code=204)
async def delete_calendar_event(event_id: int, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(CalendarEvent).where(CalendarEvent.id == event_id)
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
