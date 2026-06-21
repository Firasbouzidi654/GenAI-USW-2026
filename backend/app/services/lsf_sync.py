"""LSF-Sync — übernimmt die LSF-Mock-Daten in die Datenbank.

Mappt die zentrale LSF-Datenquelle auf die vier App-Tabellen:
    LSF-Noten                      → Grade           (Noten-/Career-Tab)
    LSF-Termine LECTURE/SEMINAR/…  → CalendarEvent   (Kalender-Tab)
    LSF-Termine EXAM/ASSIGNMENT/…  → AcademicEvent   (Planner-Tab)
    LSF-Termine EXAM               → Exam            (Prüfungen-Tab)

Idempotent: bei jedem Lauf werden die betroffenen Tabellen geleert und frisch
aus dem LSF-Mock befüllt. So bleibt die DB die Quelle für Endpunkte und Agents.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.lsf_mock import STUDENT_NAME, get_grades, get_termine
from app.models.academic_event import AcademicEvent
from app.models.calendar_event import CalendarEvent
from app.models.exam import Exam
from app.models.grade import Grade

logger = logging.getLogger(__name__)

_TZ_BERLIN = ZoneInfo("Europe/Berlin")

_CALENDAR_TYPES = {"LECTURE", "SEMINAR", "EXERCISE"}
_PLANNER_TYPES = {"EXAM", "ASSIGNMENT", "PRESENTATION"}


async def sync_lsf_to_db(db: AsyncSession) -> dict:
    """Lädt alle LSF-Daten idempotent in die Datenbank.

    Returns:
        Dict mit der Anzahl synchronisierter Datensätze pro Tabelle.
    """
    grades = get_grades()
    termine = get_termine()

    try:
        # Bestehende LSF-Daten leeren (eigene Kalender-Termine bleiben erhalten!)
        await db.execute(delete(Grade))
        await db.execute(delete(CalendarEvent).where(CalendarEvent.source == "lsf"))
        await db.execute(delete(AcademicEvent))
        await db.execute(delete(Exam))

        # Noten
        for g in grades:
            db.add(Grade(
                student_name=STUDENT_NAME,
                course_name=g.module_name,
                semester=g.semester,
                grade=g.grade,
                status=g.status,
                credits=g.ects,
                module_type="Wahlpflichtmodul" if g.type == "WP" else "Pflichtmodul",
            ))

        calendar_count = 0
        planner_count = 0
        exam_count = 0

        for t in termine:
            if t.type in _CALENDAR_TYPES:
                # Vorlesungen/Übungen → Kalender (timezone-aware Start/Ende)
                if t.start_time is None or t.end_time is None:
                    continue
                start = datetime.combine(t.date, t.start_time, tzinfo=_TZ_BERLIN)
                end = datetime.combine(t.date, t.end_time, tzinfo=_TZ_BERLIN)
                db.add(CalendarEvent(
                    uid=f"lsf:{t.id}",
                    title=t.module_name,
                    start_time=start,
                    end_time=end,
                    location=t.location,
                    description=t.title,
                    source="lsf",
                ))
                calendar_count += 1

            elif t.type in _PLANNER_TYPES:
                # Prüfungen/Abgaben/Präsentationen → Planner-Deadlines
                db.add(AcademicEvent(
                    title=t.title,
                    course_name=t.module_name,
                    type=t.type,
                    date=t.date,
                    description=t.description,
                ))
                planner_count += 1

                # Prüfungen zusätzlich in die einfache Prüfungs-Tabelle
                if t.type == "EXAM":
                    db.add(Exam(subject=t.module_name, exam_date=t.date))
                    exam_count += 1

        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("LSF-Sync fehlgeschlagen: %s", exc)
        raise

    result = {
        "synced": True,
        "grades": len(grades),
        "calendar_events": calendar_count,
        "planner_events": planner_count,
        "exams": exam_count,
    }
    logger.info("LSF-Sync abgeschlossen: %s", result)
    return result
