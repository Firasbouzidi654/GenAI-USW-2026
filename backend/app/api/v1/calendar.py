"""Kalender-Endpunkt.

Lese-Zugriff auf alle Termine (LSF-Stundenplan + eigene Termine). Eigene Termine
(``source="user"``) können angelegt und gelöscht werden; LSF-Termine sind read-only
und werden vom LSF-Sync verwaltet.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.calendar_event import CalendarEvent
from app.services.moodle_context_service import get_upcoming_moodle_deadlines

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
    category: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserEventIn(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    location: str | None = None
    description: str | None = None


class MoodleDeadlineSyncOut(BaseModel):
    created: int
    existing: int
    deadlines: list[CalendarEventOut]


class MoodleDeadlineDeleteOut(BaseModel):
    deleted: int


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
            category="User Event",
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Termin konnte nicht gespeichert werden.")


@router.post("/calendar/moodle-deadlines", response_model=MoodleDeadlineSyncOut, status_code=201)
async def sync_moodle_deadlines_to_calendar(db: AsyncSession = Depends(get_db)):
    """Legt anstehende Moodle-Deadlines als Kalendertermine an."""
    try:
        deadlines = await get_upcoming_moodle_deadlines()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Moodle-Deadlines konnten nicht geladen werden: {exc}")

    if not deadlines:
        return MoodleDeadlineSyncOut(created=0, existing=0, deadlines=[])

    uids = [
        f"moodle:{deadline['course_id']}:{deadline['title']}:{deadline['due_date']}"
        for deadline in deadlines
    ]
    try:
        result = await db.execute(select(CalendarEvent).where(CalendarEvent.uid.in_(uids)))
        existing_events = result.scalars().all()
        existing_by_uid = {event.uid: event for event in existing_events}
        created_events: list[CalendarEvent] = []

        for deadline in deadlines:
            uid = f"moodle:{deadline['course_id']}:{deadline['title']}:{deadline['due_date']}"
            if uid in existing_by_uid:
                continue
            due = datetime.fromisoformat(deadline["due_date"])
            event = CalendarEvent(
                uid=uid,
                title=deadline["title"],
                start_time=due,
                end_time=due + timedelta(minutes=15),
                location=deadline["course"],
                description=(
                    f"Course: {deadline['course']}\n"
                    "Type/category: Moodle Deadline"
                ),
                source="moodle",
                category="Moodle Deadline",
            )
            db.add(event)
            created_events.append(event)

        await db.commit()
        for event in created_events:
            await db.refresh(event)

        events = sorted([*existing_events, *created_events], key=lambda event: event.start_time)
        return MoodleDeadlineSyncOut(
            created=len(created_events),
            existing=len(existing_events),
            deadlines=events,
        )
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Moodle-Deadlines konnten nicht gespeichert werden.")


@router.delete("/calendar/moodle-deadlines", response_model=MoodleDeadlineDeleteOut)
async def delete_moodle_deadlines_from_calendar(db: AsyncSession = Depends(get_db)):
    """Löscht nur Kalendertermine, die aus Moodle-Deadlines erzeugt wurden."""
    try:
        result = await db.execute(
            delete(CalendarEvent)
            .where(CalendarEvent.source == "moodle")
            .where(CalendarEvent.category == "Moodle Deadline")
        )
        await db.commit()
        return MoodleDeadlineDeleteOut(deleted=result.rowcount or 0)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Moodle-Deadlines konnten nicht gelöscht werden.")


@router.delete("/calendar/events/{event_id}", status_code=204)
async def delete_user_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """Löscht eigene Termine und Moodle-Deadlines (LSF-Termine sind nicht löschbar)."""
    try:
        result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
        event = result.scalar_one_or_none()
        if event is None:
            raise HTTPException(status_code=404, detail="Termin nicht gefunden.")
        if event.source not in ("user", "moodle"):
            raise HTTPException(status_code=403, detail="LSF-Termine können nicht gelöscht werden.")
        await db.delete(event)
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Termin konnte nicht gelöscht werden.")
