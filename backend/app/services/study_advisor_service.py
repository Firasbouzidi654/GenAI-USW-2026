"""Study Advisor Service — generates AI study recommendations from upcoming planner events."""

from datetime import date

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.academic_event import AcademicEvent
from app.services.planner_service import get_event_priority

# Reuse the same Gemini client pattern as prompt.py
_client = genai.Client(api_key=settings.gemini_api_key)

_SYSTEM_PROMPT = """
You are an AI Study Advisor inside an Adaptive Study & Career Agent for students.

Your role:
Help the student decide what to study, what to prioritize, and how to organize their week based only on their upcoming academic events.

You receive:
1. The student's question
2. A list of upcoming academic events from the database

Each event may contain:
- title
- course_name
- type: EXAM, ASSIGNMENT, PRESENTATION
- date
- days_remaining
- priority: URGENT, HIGH, NORMAL
- description

Rules:
- Do not invent events, deadlines, exams, or grades.
- Use only the events provided in the context.
- If there are no upcoming events, tell the student to add events in the Planner first.
- Prioritize events by urgency and date.
- URGENT events must come first.
- HIGH priority events come after urgent events.
- NORMAL priority events can be planned with less intensity.
- Give practical and realistic advice.
- Keep the answer short, clear, and student-friendly.
- Do not create a complicated timetable unless the user asks for a full weekly plan.
- If the user asks what to do today, give 1 to 3 concrete tasks.
- If the user asks for this week, create a simple weekly plan.
- If the user asks about risk, explain which deadline is most risky and why.
- If multiple deadlines are close together, recommend workload distribution in percentages.
- Always explain the reason behind the priority.
- End with a short actionable recommendation.

Response style:
- Use clear headings
- Use short bullet points
- Avoid long paragraphs
- Be motivating but realistic
- Do not be too verbose
""".strip()

_FALLBACK = "The Study Advisor is temporarily unavailable. Please try again later."
_NO_EVENTS = (
    "You have no upcoming academic events in your Planner yet. "
    "Please add your exams, assignments, and presentations in the Planner tab first, "
    "and I will help you prioritize them."
)


def _build_events_context(events: list[AcademicEvent]) -> str:
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


async def get_study_advice(message: str, db: AsyncSession) -> str:
    today = date.today()
    result = await db.execute(
        select(AcademicEvent)
        .where(AcademicEvent.date >= today)
        .order_by(AcademicEvent.date)
    )
    events = result.scalars().all()

    if not events:
        return _NO_EVENTS

    events_context = _build_events_context(events)
    full_prompt = (
        f"Student's upcoming academic events:\n{events_context}"
        f"\n\nStudent question: {message}"
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
