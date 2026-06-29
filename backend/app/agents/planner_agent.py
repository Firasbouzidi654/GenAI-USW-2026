"""PlannerAgent — erstellt intelligente Lernpläne unter Berücksichtigung von
Stundenplan, Prüfungsterminen und Noten.

Nutzt LangChain 1.x `create_agent`. Der Agent ruft selbstständig Planner-Events,
Kalender-Events und Noten ab und plant Lernzeiten um belegte Slots herum.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from langgraph.prebuilt import create_react_agent as create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import extract_text_output, get_llm
from app.models.academic_event import AcademicEvent
from app.models.calendar_event import CalendarEvent
from app.models.grade import Grade
from app.services.moodle_context_service import get_moodle_deadlines_context, get_next_moodle_deadline_context, get_moodle_courses_context
from app.services.planner_service import get_event_priority

logger = logging.getLogger(__name__)

_TZ_BERLIN = ZoneInfo("Europe/Berlin")
_CALENDAR_WINDOW_DAYS = 14

_SYSTEM_PROMPT = """
Du bist ein intelligenter Lernplan-Agent (Planner Agent) für Studierende an der HTW Berlin.

Du hast Zugriff auf:
- Den Stundenplan (Kalender-Events: Vorlesungen, Seminare, Übungen)
- Akademische Deadlines und Prüfungstermine (Planner-Events aus LSF)
- Moodle-Abgaben und Deadlines (get_moodle_deadlines — ergänzt LSF-Termine)
- Noten und Leistungsstand

Kernregeln:
- Vorlesungszeiten sind GESPERRT — plane NIEMALS in Unterrichtszeiten
- Priorisiere URGENT (≤7 Tage) → HIGH (≤14 Tage) → NORMAL
- Plane konkrete Zeitblöcke mit Themen (z.B. "Di 14–16 Uhr: Analysis Kapitel 3")
- Wenn Prüfung und Vorlesung am gleichen Tag: explizit hinweisen
- Sei realistisch: max. 6–8h Lernzeit pro Tag
- Empfehle Pomodoro-Technik (25min/5min) für konzentriertes Lernen

Antworte auf Deutsch mit klarer Struktur (Abschnitte und Aufzählungen).
Falls keine Daten vorhanden: erkläre was der Studierende im Planner/Kalender erfassen soll.
""".strip()


def create_planner_agent(db: AsyncSession):
    """Erstellt einen PlannerAgent (LangGraph CompiledStateGraph)."""

    @tool
    async def get_upcoming_deadlines() -> str:
        """Ruft alle bevorstehenden akademischen Deadlines ab:
        Prüfungen, Abgaben, Präsentationen — mit Priorität und verbleibenden Tagen."""
        try:
            today = date.today()
            result = await db.execute(
                select(AcademicEvent)
                .where(AcademicEvent.date >= today)
                .order_by(AcademicEvent.date)
            )
            events = result.scalars().all()
            if not events:
                return "Keine bevorstehenden Deadlines im Planner gefunden."

            output = []
            for e in events:
                p = get_event_priority(e.date)
                entry = {
                    "title": e.title,
                    "course": e.course_name,
                    "type": e.type,
                    "date": str(e.date),
                    "days_remaining": p["days_remaining"],
                    "priority": p["priority"],
                }
                if e.description:
                    entry["notes"] = e.description
                output.append(entry)
            return json.dumps(output, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Deadline-Abfrage fehlgeschlagen: %s", exc)
            return "Deadlines konnten nicht abgerufen werden."

    @tool
    async def get_calendar_schedule(days_ahead: int = 14) -> str:
        """Ruft den Stundenplan für die nächsten N Tage ab.
        Diese Zeiten sind GESPERRT und nicht zum Lernen verfügbar.

        Args:
            days_ahead: Tage in die Zukunft (max 14, Standard: 14)
        """
        try:
            now = datetime.now(timezone.utc)
            window = min(days_ahead, _CALENDAR_WINDOW_DAYS)
            end = now + timedelta(days=window)

            result = await db.execute(
                select(CalendarEvent)
                .where(CalendarEvent.start_time >= now)
                .where(CalendarEvent.start_time <= end)
                .order_by(CalendarEvent.start_time)
            )
            events = result.scalars().all()
            if not events:
                return f"Keine Kalender-Events in den nächsten {window} Tagen gefunden."

            output = []
            for e in events:
                start = e.start_time.astimezone(_TZ_BERLIN)
                end_t = e.end_time.astimezone(_TZ_BERLIN)
                entry = {
                    "title": e.title,
                    "date": start.strftime("%A %d.%m.%Y"),
                    "start": start.strftime("%H:%M"),
                    "end": end_t.strftime("%H:%M"),
                    "blocked": True,
                }
                if e.location:
                    entry["location"] = e.location
                output.append(entry)
            return json.dumps(output, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Kalender-Abfrage fehlgeschlagen: %s", exc)
            return "Stundenplan konnte nicht abgerufen werden."

    @tool
    async def get_grade_summary() -> str:
        """Gibt eine Notenübersicht zurück — hilft einzuschätzen, wo mehr Lernzeit nötig ist.
        Schlechte Noten (≥4.0) bedeuten mehr Nachholbedarf."""
        try:
            result = await db.execute(select(Grade))
            grades = result.scalars().all()
            if not grades:
                return "Keine Noten eingetragen."

            output = []
            for g in grades:
                entry = {"course": g.course_name}
                if g.grade:
                    entry["grade"] = g.grade
                    try:
                        grade_val = float(g.grade.replace(",", "."))
                        entry["needs_attention"] = grade_val >= 4.0
                        entry["good"] = grade_val <= 2.0
                    except ValueError:
                        pass
                if g.semester:
                    entry["semester"] = g.semester
                if g.credits:
                    entry["credits"] = g.credits
                output.append(entry)
            return json.dumps(output, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Noten-Abfrage fehlgeschlagen: %s", exc)
            return "Noten konnten nicht abgerufen werden."

    @tool
    async def get_moodle_deadlines(course_name: str = "") -> str:
        """Ruft Moodle-Abgabefristen ab. Ohne Kursname: nächste fällige Abgabe über alle Kurse.
        Mit Kursname: alle Abgaben für diesen Kurs (offen und vergangen).

        Args:
            course_name: Kursname oder leer für die nächste globale Deadline.
        """
        if course_name.strip():
            return await get_moodle_deadlines_context(course_name)
        return await get_next_moodle_deadline_context()

    @tool
    async def get_moodle_courses() -> str:
        """Listet alle belegten Moodle-Kurse des Studierenden."""
        return await get_moodle_courses_context()

    llm = get_llm(temperature=0.3)
    return create_agent(
        model=llm,
        tools=[get_upcoming_deadlines, get_calendar_schedule, get_grade_summary,
               get_moodle_deadlines, get_moodle_courses],
        prompt=_SYSTEM_PROMPT,
    )


async def run_planner_agent(message: str, db: AsyncSession) -> str:
    """Führt den PlannerAgent aus und gibt Lernplan-Empfehlungen zurück."""
    agent = create_planner_agent(db)
    try:
        result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
        return extract_text_output(result) or "Der Lernplan konnte nicht erstellt werden."
    except Exception as exc:
        logger.error("PlannerAgent fehlgeschlagen: %s", exc)
        return "Der Lernplan-Agent ist momentan nicht erreichbar. Bitte später erneut versuchen."
