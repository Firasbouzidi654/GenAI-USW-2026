"""Study Advisor Service — generates AI study recommendations from planner events and calendar classes."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.academic_event import AcademicEvent
from app.models.calendar_event import CalendarEvent
from app.services.planner_service import get_event_priority

_client = genai.Client(api_key=settings.gemini_api_key)

_SYSTEM_PROMPT = """
You are an AI Study Advisor inside an Adaptive Study & Career Agent for students.

Your role:
Help the student decide what to study, what to prioritize, and how to organize their week.
You base your advice strictly on the upcoming deadlines and scheduled calendar classes provided below.

You receive:
1. The student's question
2. Upcoming academic deadlines (from the Planner)
3. Upcoming scheduled calendar classes for the next 7 days (from the Kalender)

Planner event fields:
- title, course_name, type (EXAM / ASSIGNMENT / PRESENTATION), date, days_remaining, priority (URGENT / HIGH / NORMAL), description

Calendar class fields:
- title (course/module name), date, start_time, end_time, location

Rules — general:
- Do not invent events, deadlines, classes, or grades. Use only the data provided.
- If neither planner events nor calendar classes are available, ask the student to add Planner events or import their calendar first.
- If no planner events exist but calendar classes are available, acknowledge the classes and note that no deadlines have been added yet.
- If planner events exist but no calendar classes are available, give a pure priority-based study plan.
- Prioritize deadlines: URGENT first, HIGH second, NORMAL with lower intensity.
- Always explain the reason behind the priority.
- End with a short actionable recommendation.

Rules — calendar-aware planning:
- Do not schedule study time during a calendar class. Treat class time as blocked.
- When a student has a class on a certain day, recommend studying before or after that class.
- Mention specific class times when they affect the study plan (e.g. "You have Webtechnologien from 08:00 to 09:30 on Friday, so use the afternoon for project work").
- If a deadline is due the same day as a class, flag this explicitly.
- When creating a weekly plan, map each day to its known classes and assign study blocks around them.

Rules — response style and length:
- Keep answers short, clear, and student-friendly.
- Use clear headings and short bullet points.
- Avoid long paragraphs.
- Be motivating but realistic.
- Do not create a complicated timetable unless the student explicitly asks for a full weekly plan.
- If the student asks "what to do today", give 1–3 concrete tasks and note any class they have today.
- If the student asks "this week", create a simple day-by-day plan around their classes.
- If the student asks about risk, explain which deadline is most at risk and why.
- If multiple deadlines are close, recommend workload distribution in percentages.
""".strip()

_FALLBACK = "The Study Advisor is temporarily unavailable. Please try again later."

_NO_DATA = (
    "You have no upcoming deadlines in your Planner and no calendar classes in the next 7 days. "
    "Please add your exams, assignments, and presentations in the Planner tab, "
    "or import your timetable in the Kalender tab — then I can help you plan."
)

_CALENDAR_WINDOW_DAYS = 7
_TZ_BERLIN = ZoneInfo("Europe/Berlin")


def _build_planner_context(events: list[AcademicEvent]) -> str:
    lines: list[str] = []
    for e in events:
        p = get_event_priority(e.date)
        line = (
            f"- Title: {e.title} | Course: {e.course_name} | Type: {e.type} "
            f"| Date: {e.date} | Days remaining: {p['days_remaining']} | Priority: {p['priority']}"
        )
        if e.description:
            line += f" | Notes: {e.description}"
        lines.append(line)
    return "\n".join(lines)


def _build_calendar_context(events: list[CalendarEvent]) -> str:
    lines: list[str] = []
    for e in events:
        # Convert to Europe/Berlin so the times Gemini sees match exactly what
        # the Kalender tab displays (the frontend uses toLocaleTimeString('de-DE')
        # which also converts UTC → local/Berlin time).
        start = e.start_time.astimezone(_TZ_BERLIN)
        end = e.end_time.astimezone(_TZ_BERLIN)
        date_str = start.strftime("%A %d.%m.%Y")
        time_str = f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
        line = f"- {e.title} | {date_str} | {time_str}"
        if e.location:
            line += f" | Location: {e.location}"
        lines.append(line)
    return "\n".join(lines)


async def get_study_advice(message: str, db: AsyncSession) -> str:
    today = date.today()
    now = datetime.now(timezone.utc)
    week_end = now + timedelta(days=_CALENDAR_WINDOW_DAYS)

    # --- Fetch upcoming planner deadlines ---
    planner_result = await db.execute(
        select(AcademicEvent)
        .where(AcademicEvent.date >= today)
        .order_by(AcademicEvent.date)
    )
    planner_events = planner_result.scalars().all()

    # --- Fetch calendar classes for the next 7 days (safe: fallback to empty on any DB error) ---
    try:
        calendar_result = await db.execute(
            select(CalendarEvent)
            .where(CalendarEvent.start_time >= now)
            .where(CalendarEvent.start_time <= week_end)
            .order_by(CalendarEvent.start_time)
        )
        calendar_events = calendar_result.scalars().all()
    except Exception:
        calendar_events = []

    # --- Handle no-data cases ---
    if not planner_events and not calendar_events:
        return _NO_DATA

    # --- Build context sections ---
    if planner_events:
        planner_section = f"Upcoming deadlines (Planner):\n{_build_planner_context(planner_events)}"
    else:
        planner_section = "Upcoming deadlines (Planner): None — no deadlines have been added yet."

    if calendar_events:
        calendar_section = (
            f"Scheduled calendar classes for the next {_CALENDAR_WINDOW_DAYS} days (Kalender):\n"
            f"{_build_calendar_context(calendar_events)}"
        )
    else:
        calendar_section = f"Scheduled calendar classes (next {_CALENDAR_WINDOW_DAYS} days): None imported."

    full_prompt = (
        f"{planner_section}\n\n"
        f"{calendar_section}\n\n"
        f"Student question: {message}"
    )

    try:
        response = await _client.aio.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=full_prompt,
            config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
        )
        return response.text or _FALLBACK
    except Exception:
        return _FALLBACK
