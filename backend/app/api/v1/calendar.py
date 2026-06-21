"""Kalender-Endpunkt.

Lese-Zugriff auf alle Termine (LSF-Stundenplan + eigene Termine). Eigene Termine
(``source="user"``) können angelegt und gelöscht werden; LSF-Termine sind read-only
und werden vom LSF-Sync verwaltet.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.calendar_event import CalendarEvent

router = APIRouter()


class CalendarEventOut(BaseModel):
    id: int
    uid: str
    title: str
    start_time: datetime
    end_time: datetime
    location: str | None
    description: str | None
    source: str = "lsf"
    created_at: datetime

    model_config = {"from_attributes": True}


class UserEventIn(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    location: str | None = None
    description: str | None = None


@router.get("/calendar/events", response_model=list[CalendarEventOut])
async def get_calendar_events(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(CalendarEvent).order_by(CalendarEvent.start_time)
        )
        return result.scalars().all()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.post("/calendar/events", response_model=CalendarEventOut, status_code=201)
async def create_user_event(body: UserEventIn, db: AsyncSession = Depends(get_db)):
    """Legt einen eigenen Termin an (wird im Kalender markiert + bei der Planung berücksichtigt)."""
    if body.end_time <= body.start_time:
        raise HTTPException(status_code=422, detail="Ende muss nach dem Start liegen.")
    try:
        event = CalendarEvent(
            uid=f"user:{datetime.now().timestamp()}",
            title=body.title.strip() or "Termin",
            start_time=body.start_time,
            end_time=body.end_time,
            location=(body.location or "").strip() or None,
            description=(body.description or "").strip() or None,
            source="user",
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Termin konnte nicht gespeichert werden.")


@router.delete("/calendar/events/{event_id}", status_code=204)
async def delete_user_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """Löscht einen eigenen Termin (LSF-Termine sind nicht löschbar)."""
    try:
        result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
        event = result.scalar_one_or_none()
        if event is None:
            raise HTTPException(status_code=404, detail="Termin nicht gefunden.")
        if event.source != "user":
            raise HTTPException(status_code=403, detail="LSF-Termine können nicht gelöscht werden.")
        await db.delete(event)
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Termin konnte nicht gelöscht werden.")
