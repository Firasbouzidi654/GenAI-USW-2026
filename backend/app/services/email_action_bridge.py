"""Architecture placeholder for a future "add to Planner / Calendar" action.

Not wired up yet - nothing here calls the database or any endpoint. These are
pure, side-effect-free mapping functions that convert Email-Agent digest
entries (urgent_actions / events, see email_summary_service.py) into the exact
request shapes the existing Planner and Calendar endpoints already expect:

- AcademicEventIn  (app/api/v1/planner.py)  - title, course_name, type, date, description
- CalendarEventIn  (app/api/v1/calendar.py) - uid, title, start_time, end_time, location, description

When the "Add to Planner" / "Add to Calendar" frontend buttons are built, the
new endpoint(s) can call these mappers and then reuse the existing
create-event code paths instead of duplicating them. Deliberately not done
yet: deadline/date strings from Gemini are free text (e.g. "Mittwoch, 17. Juni
2026, 19:00") and need real parsing/validation before they can satisfy
AcademicEventIn.date / CalendarEventIn.start_time - that work belongs with
the actual integration, not this placeholder.
"""

from __future__ import annotations


def urgent_action_to_academic_event(action: dict, course_name: str = "E-Mail") -> dict:
    """Maps an urgent_actions[] entry to the AcademicEventIn shape.

    `date` is left as the raw Gemini string - parse/validate before sending
    to POST /api/planner/events once that integration is built.
    """
    return {
        "title": action.get("title", ""),
        "course_name": course_name,
        "type": "ASSIGNMENT",
        "date": action.get("deadline", ""),
        "description": action.get("reason", ""),
    }


def event_to_calendar_event(event: dict) -> dict:
    """Maps an events[] entry to the CalendarEventIn shape.

    `start_time`/`end_time` are left as the raw Gemini date string - parse/
    validate before sending to POST /api/calendar/events once that
    integration is built. `uid` is intentionally omitted; the caller should
    generate one (e.g. a hash of title+date) to keep it idempotent.
    """
    return {
        "title": event.get("title", ""),
        "start_time": event.get("date", ""),
        "end_time": event.get("date", ""),
        "location": event.get("location", ""),
        "description": "",
    }
