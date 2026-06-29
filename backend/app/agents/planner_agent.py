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
from app.services.moodle_context_service import (
    get_moodle_courses_context,
    get_moodle_deadlines_context,
    get_upcoming_moodle_deadlines_context,
)
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


def _message_role(msg) -> str:
    role = getattr(msg, "type", None) or getattr(msg, "role", None)
    if role:
        return str(role).lower()
    class_name = msg.__class__.__name__.lower()
    if "tool" in class_name:
        return "tool"
    if "ai" in class_name or "assistant" in class_name:
        return "ai"
    return class_name


def _parse_json_payload(value: str):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _looks_like_raw_json(value: str) -> bool:
    text = (value or "").strip()
    return (text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}"))


def _grade_value(item: dict) -> float | None:
    grade = item.get("grade")
    if not grade:
        return None
    try:
        return float(str(grade).replace(",", "."))
    except ValueError:
        return None


def _format_grade_focus(payload: list[dict]) -> str:
    graded = [item for item in payload if isinstance(item, dict) and _grade_value(item) is not None]
    if not graded:
        return ""

    focus = sorted(
        [item for item in graded if item.get("needs_attention") or not item.get("good")],
        key=lambda item: _grade_value(item) or 0,
        reverse=True,
    )
    if not focus:
        focus = sorted(graded, key=lambda item: _grade_value(item) or 0, reverse=True)[:3]
    else:
        focus = focus[:4]

    strong = sorted(
        [item for item in graded if item.get("good")],
        key=lambda item: _grade_value(item) or 99,
    )[:3]

    lines = ["Diese Woche solltest du dich auf die Faecher mit dem groessten Verbesserungspotenzial konzentrieren:"]
    for idx, item in enumerate(focus, start=1):
        semester = f", {item['semester']}" if item.get("semester") else ""
        lines.append(f"{idx}. {item['course']} (Note {item['grade']}{semester})")

    lines.extend(
        [
            "",
            "Vorschlag fuer deinen Fokus:",
            "- Plane zuerst 2-3 konzentrierte Lernbloecke fuer die oben genannten Faecher.",
            "- Wiederhole danach kurz die starken Faecher, damit der Stand stabil bleibt.",
            "- Wenn eine konkrete Deadline oder Pruefung naeherrueckt, priorisiere dieses Fach zuerst.",
        ]
    )
    if strong:
        strong_courses = ", ".join(str(item["course"]) for item in strong)
        lines.append(f"Starke Faecher wie {strong_courses} reichen diese Woche eher fuer kurze Wiederholung.")
    return "\n".join(lines)


def _format_deadline_focus(payload: list[dict]) -> str:
    deadlines = [
        item for item in payload
        if isinstance(item, dict) and item.get("title") and (item.get("date") or item.get("days_remaining") is not None)
    ]
    if not deadlines:
        return ""
    lines = ["Diese Woche solltest du dich an den naechsten Terminen orientieren:"]
    for idx, item in enumerate(deadlines[:5], start=1):
        course = f" - {item['course']}" if item.get("course") else ""
        days = f", noch {item['days_remaining']} Tage" if item.get("days_remaining") is not None else ""
        lines.append(f"{idx}. {item['title']}{course}: {item.get('date', 'kein Datum')}{days}")
    lines.extend(
        [
            "",
            "Arbeite zuerst an den Terminen mit hoher Prioritaet und blocke dafuer feste Lernzeiten im Kalender.",
        ]
    )
    return "\n".join(lines)


def _format_schedule_focus(payload: list[dict]) -> str:
    slots = [item for item in payload if isinstance(item, dict) and item.get("blocked")]
    if not slots:
        return ""
    lines = ["Dein Stundenplan blockiert in den naechsten Tagen diese Zeiten:"]
    for item in slots[:5]:
        lines.append(
            f"- {item.get('date', 'Datum offen')}, {item.get('start', '?')}-{item.get('end', '?')}: "
            f"{item.get('title', 'Termin')}"
        )
    lines.append("\nPlane Lernbloecke um diese Zeiten herum, nicht parallel dazu.")
    return "\n".join(lines)


def _format_internal_payload(payload) -> str:
    if isinstance(payload, list):
        for formatter in (_format_grade_focus, _format_deadline_focus, _format_schedule_focus):
            formatted = formatter(payload)
            if formatted:
                return formatted
    return ""


def _format_planner_tool_fallback(agent_result: dict) -> str:
    for msg in reversed(agent_result.get("messages", [])):
        if _message_role(msg) != "tool":
            continue
        payload = _parse_json_payload(getattr(msg, "content", ""))
        formatted = _format_internal_payload(payload)
        if formatted:
            return formatted
    return ""


def _format_raw_json_fallback(text: str) -> str:
    payload = _parse_json_payload(text)
    return _format_internal_payload(payload)


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
        """Ruft Moodle-Abgabefristen ab. Ohne Kursname: alle anstehenden Abgaben über alle Kurse.
        Mit Kursname: alle Abgaben für diesen Kurs (offen und vergangen).

        Args:
            course_name: Kursname oder leer für alle anstehenden globalen Deadlines.
        """
        if course_name.strip():
            return await get_moodle_deadlines_context(course_name)
        return await get_upcoming_moodle_deadlines_context()

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
        answer = extract_text_output(result)
        if answer and not _looks_like_raw_json(answer):
            return answer
        if answer:
            formatted = _format_raw_json_fallback(answer)
            if formatted:
                return formatted
        return _format_planner_tool_fallback(result) or "Der Lernplan konnte nicht erstellt werden."
    except Exception as exc:
        logger.error("PlannerAgent fehlgeschlagen: %s", exc)
        return "Der Lernplan-Agent ist momentan nicht erreichbar. Bitte später erneut versuchen."
