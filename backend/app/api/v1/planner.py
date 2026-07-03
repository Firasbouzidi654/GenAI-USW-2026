"""Planner-Endpunkt.

Liest die Deadlines (aus dem LSF-Mock) und erzeugt auf Wunsch über den PlannerAgent
einen konkreten, zeitlich geblockten Lernplan (berücksichtigt Vorlesungen, eigene
Termine und Deadlines).
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.agents.planner_agent import run_planner_agent
from app.core.database import get_db
from app.models.academic_event import AcademicEvent
from app.services.planner_service import get_event_priority

router = APIRouter()


class StudyPlanRequest(BaseModel):
    horizon_days: int = Field(7, ge=1, le=21)


class StudyPlanResponse(BaseModel):
    plan: str


_STUDY_PLAN_PROMPT = (
    "Erstelle mir einen konkreten, zeitlich geblockten Lernplan für die nächsten "
    "{days} Tage. Sage mir für jeden Tag genau: zu welcher UHRZEIT, WIE LANGE und WAS "
    "ich lernen soll (in Lernblöcken, z.B. 'Di 16:00–17:30 Datenbanken wiederholen'). "
    "Berücksichtige meine Vorlesungen/Übungen und meine eigenen Termine als bereits "
    "belegte Zeiten (NICHT überschneiden) und priorisiere nach den anstehenden Deadlines. "
    "Plane realistische Pausen ein. Gib das Ergebnis als übersichtliche Liste pro Tag aus."
)


@router.post("/planner/study-plan", response_model=StudyPlanResponse)
async def create_study_plan(body: StudyPlanRequest, db: AsyncSession = Depends(get_db)):
    """Generiert einen zeitlich geblockten Lernplan über den PlannerAgent."""
    plan = await run_planner_agent(_STUDY_PLAN_PROMPT.format(days=body.horizon_days), db)
    return {"plan": plan}


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
