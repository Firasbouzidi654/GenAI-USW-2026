"""Lightweight Moodle context helpers for the Orchestrator.

This module deliberately does not create an agent, persist data, or duplicate
Moodle API logic. It formats live data returned by ``moodle_service.py`` so the
chat can answer explicit Moodle questions without touching the existing areas
or specialized agents.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.services import moodle_service

_TZ_BERLIN = ZoneInfo("Europe/Berlin")

_SEMESTER_COURSE_IDS = {
    5: {"60415", "59507", "58776", "58690"},
}
_SEMESTER_5_COURSE_IDS = _SEMESTER_COURSE_IDS[5]

_SEMESTER_KEYWORDS = {
    1: (
        "grundlagen der programmierung",
        "rechnernetze",
        "einfuehrung in die bwl",
        "einführung in die bwl",
        "einfuehrung in die vwl",
        "einführung in die vwl",
        "einfuehrung in die wirtschaftsinformatik",
        "einführung in die wirtschaftsinformatik",
        "grundlagen des software-engineering",
        "mathematik",
    ),
    2: (
        "angewandte programmierung",
        "datenmodellierung",
        "datenbanksysteme",
        "unternehmens- und personalmanagement",
        "buchfuehrung und bilanzen",
        "buchführung und bilanzen",
        "grundlagen projektmanagement",
        "geschaeftsprozesse",
        "geschäftsprozesse",
        "betriebliche anwendungen",
    ),
    3: (
        "webtechnologien",
        "datenbanktechnologien",
        "controlling",
        "modellierung von anwendungssystemen",
        "statistik",
        "fremdsprache",
    ),
    4: (
        "investition und finanzierung",
        "wahlpflichtmodul soft skills",
        "konfliktmanagement",
        "fachpraktikum",
        "praktikum",
    ),
    5: (
        "verteilte anwendungen",
        "produktionswirtschaft",
        "logistik",
        "unternehmenssoftware",
        "wahlpflichtmodul informatik",
        "awe",
        "life-hacking",
        "fremdsprache",
    ),
    6: (
        "bachelorarbeit",
        "bachelorseminar",
        "abschlusskolloquium",
        "wahlpflichtmodul wirtschaftsinformatik",
        "ausgewaehlte themen der wirtschaftsinformatik",
        "ausgewählte themen der wirtschaftsinformatik",
        "awe-modul 2",
    ),
}


def _not_configured_message() -> str:
    return "Moodle ist nicht verbunden (kein MOODLE_TOKEN konfiguriert)."


def _extract_course_id(value: str | int | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    match = re.search(r"\b(?:course\s*)?(\d{3,})\b", text, re.IGNORECASE)
    return match.group(1) if match else None


def _course_label(course: dict) -> str:
    name = course.get("fullname") or course.get("shortname") or "Unbenannter Moodle-Kurs"
    course_id = course.get("id")
    shortname = course.get("shortname")
    semester = course.get("semester")
    suffix = []
    if shortname and shortname != name:
        suffix.append(f"Shortname: {shortname}")
    if course_id is not None:
        suffix.append(f"ID: {course_id}")
    if semester:
        suffix.append(str(semester))
    return f"{name} ({', '.join(suffix)})" if suffix else name


def _short_course_name(course: dict) -> str:
    name = course.get("fullname") or course.get("shortname") or "Moodle-Kurs"
    return str(name).split(" - ", 1)[0].strip()


async def _load_courses() -> list[dict] | str:
    if not moodle_service.is_configured():
        return _not_configured_message()
    try:
        return await moodle_service.get_moodle_courses()
    except moodle_service.MoodleError as exc:
        return f"Moodle-Kurse konnten nicht geladen werden: {exc}"


def _match_course(courses: list[dict], course_id_or_course_name: str | int | None) -> dict | None:
    if not courses:
        return None
    if course_id_or_course_name is None:
        return None

    query = str(course_id_or_course_name).strip()
    course_id = _extract_course_id(query)
    if course_id:
        for course in courses:
            if str(course.get("id")) == course_id:
                return course

    q = query.lower()
    if "unternehmenssoftware" in q:
        for course in courses:
            haystack = f"{course.get('fullname', '')} {course.get('shortname', '')}".lower()
            if str(course.get("id")) == "58776" or "unternehmenssoftware" in haystack:
                return course

    stop_words = (
        "moodle", "kurs", "course", "module", "modules", "modul", "module",
        "overview", "materials", "materialien", "grades", "noten", "deadline",
        "aufgabe", "aufgaben", "erklaer", "erklär", "mir", "den", "die", "das",
        "for", "my", "show", "what", "is", "next", "naechste", "nächste",
    )
    cleaned = q
    for word in stop_words:
        cleaned = re.sub(rf"\b{re.escape(word)}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .:;-")

    if cleaned:
        for course in courses:
            haystack = f"{course.get('fullname', '')} {course.get('shortname', '')}".lower()
            if cleaned in haystack:
                return course

        query_words = set(cleaned.split())
        best, best_overlap = None, 0
        for course in courses:
            haystack = f"{course.get('fullname', '')} {course.get('shortname', '')}".lower()
            overlap = len(query_words & set(haystack.split()))
            if overlap > best_overlap:
                best, best_overlap = course, overlap
        if best_overlap:
            return best

    return None


def _is_semester_5_query(value: str | int | None) -> bool:
    text = str(value or "").lower()
    return (
        "5. semester" in text
        or "5 semester" in text
        or "semester 5" in text
        or "fuenftes semester" in text
        or "fünftes semester" in text
        or "sose 2026" in text
        or "sose2026" in text
    )


def _filter_semester_5_courses(courses: list[dict]) -> list[dict]:
    return [course for course in courses if str(course.get("id")) in _SEMESTER_5_COURSE_IDS]


def _extract_requested_semester(value: str | int | None) -> int | None:
    text = str(value or "").lower()
    match = re.search(r"\b(?:semester|sem)\s*(\d)\b|\b(\d)\.?\s*semester\b", text)
    if match:
        number = match.group(1) or match.group(2)
        if number:
            return int(number)
    ordinal_map = {
        "erstes semester": 1,
        "zweites semester": 2,
        "drittes semester": 3,
        "viertes semester": 4,
        "fuenftes semester": 5,
        "sechstes semester": 6,
    }
    for phrase, semester in ordinal_map.items():
        if phrase in text:
            return semester
    if "sose 2026" in text or "sose2026" in text:
        return 5
    return None


def _detect_course_semester(course: dict) -> int | str:
    course_id = str(course.get("id"))
    for semester, course_ids in _SEMESTER_COURSE_IDS.items():
        if course_id in course_ids:
            return semester

    text = f"{course.get('fullname', '')} {course.get('shortname', '')}".lower()
    for semester, keywords in _SEMESTER_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return semester
    return "other"


def _filter_courses_by_semester(courses: list[dict], semester: int) -> list[dict]:
    return [course for course in courses if _detect_course_semester(course) == semester]


def _extract_explicit_course_reference(message: str | int | None) -> str | None:
    """Return a course reference only when the user clearly names one."""
    if message is None:
        return None
    text = str(message).strip()
    course_id = _extract_course_id(text)
    if course_id:
        return course_id

    lowered = text.lower()
    known_terms = (
        "unternehmenssoftware",
        "webtechnologien",
        "produktionswirtschaft",
        "logistik",
        "life-hacking",
        "life hacking",
        "awe",
    )
    for term in known_terms:
        if term in lowered:
            return term

    match = re.search(r"\b(?:für|fuer|for|kurs|course)\s+(.+)$", text, re.IGNORECASE)
    if match:
        candidate = re.sub(r"[?.!]+$", "", match.group(1)).strip()
        if candidate:
            return candidate
    return None


async def _resolve_course(course_id_or_course_name: str | int | None) -> dict | str | None:
    courses = await _load_courses()
    if isinstance(courses, str):
        return courses
    return _match_course(courses, course_id_or_course_name)


def _parse_due_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _format_due_date(value: Any) -> str:
    parsed = _parse_due_date(value)
    if parsed is None:
        return str(value) if value else "kein Datum"
    parsed = parsed.astimezone(_TZ_BERLIN)
    return parsed.strftime("%d.%m.%Y, %H:%M")


def _item_type(item: dict) -> str:
    return str(item.get("type") or item.get("modname") or "item")


def _deadline_sort_key(deadline: dict) -> datetime:
    return _parse_due_date(deadline.get("due_date")) or datetime.max.replace(tzinfo=timezone.utc)


async def get_moodle_courses_context(course_id_or_course_name: str | int | None = None) -> str:
    """Return a compact list of enrolled Moodle courses."""
    courses = await _load_courses()
    if isinstance(courses, str):
        return courses
    if not courses:
        return "Keine Moodle-Kurse gefunden."
    requested_semester = _extract_requested_semester(course_id_or_course_name)
    if requested_semester is not None:
        courses = _filter_courses_by_semester(courses, requested_semester)
        if not courses:
            return f"Keine Moodle-Kurse fuer Semester {requested_semester} gefunden."
        return f"Moodle-Kurse fuer Semester {requested_semester}:\n" + "\n".join(
            f"{idx}. {_course_label(course)}" for idx, course in enumerate(courses, start=1)
        )
    return "Moodle-Kurse:\n" + "\n".join(f"- {_course_label(course)}" for course in courses)


async def get_next_moodle_deadline_context(
    course_id_or_course_name: str | int | None = None,
) -> str:
    """Return the next live Moodle deadline, optionally restricted to one course."""
    courses = await _load_courses()
    if isinstance(courses, str):
        return courses
    if not courses:
        return "Keine Moodle-Kurse gefunden."

    explicit_course = _extract_explicit_course_reference(course_id_or_course_name)
    matched = _match_course(courses, explicit_course)
    selected_courses = [matched] if matched else courses
    candidates: list[tuple[datetime, dict, dict]] = []

    for course in selected_courses:
        if course is None:
            continue
        try:
            result = await moodle_service.get_moodle_course_deadlines(str(course.get("id")))
        except moodle_service.MoodleError:
            continue
        for deadline in result.get("deadlines", []) if isinstance(result, dict) else []:
            due = _parse_due_date(deadline.get("due_date"))
            if due is None:
                continue
            candidates.append((due, deadline, course))

    if not candidates:
        if matched:
            return f"Keine Moodle-Aufgaben fuer {matched.get('fullname')} gefunden."
        return "Keine Moodle-Aufgaben gefunden."

    now = datetime.now(timezone.utc)
    future = [candidate for candidate in candidates if candidate[0] >= now]
    if not future:
        return "Keine anstehenden Moodle-Aufgaben gefunden."

    due, deadline, course = sorted(future, key=lambda item: item[0])[0]
    return (
        "Nächste Moodle-Aufgabe:\n\n"
        f"{deadline.get('name', 'Unbenannte Moodle-Aufgabe')}\n"
        f"Kurs: {_short_course_name(course)}\n"
        f"Datum: {_format_due_date(deadline.get('due_date'))}"
    )


async def get_moodle_deadlines_context(course_id_or_course_name: str | int) -> str:
    """Return all Moodle deadlines for one explicit course grouped by status."""
    courses = await _load_courses()
    if isinstance(courses, str):
        return courses
    if not courses:
        return "Keine Moodle-Kurse gefunden."

    explicit_course = _extract_explicit_course_reference(course_id_or_course_name)
    matched = _match_course(courses, explicit_course)
    if matched is None:
        return "Kein passender Moodle-Kurs gefunden. Bitte gib Kursname oder Course ID an."

    try:
        result = await moodle_service.get_moodle_course_deadlines(str(matched.get("id")))
    except moodle_service.MoodleError as exc:
        return f"Moodle-Deadlines konnten nicht geladen werden: {exc}"

    deadlines = result.get("deadlines", []) if isinstance(result, dict) else []
    if not deadlines:
        return f"Keine Moodle-Deadlines fuer {_short_course_name(matched)} gefunden."

    now = datetime.now(timezone.utc)
    past = []
    upcoming = []
    for deadline in deadlines:
        due = _parse_due_date(deadline.get("due_date"))
        if due is not None and due < now:
            past.append(deadline)
        else:
            upcoming.append(deadline)

    lines = [f"Moodle-Deadlines für {_short_course_name(matched)}:"]
    if past:
        lines.extend(["", "Bereits vergangen:"])
        lines.extend(
            f"- {deadline.get('name', 'Unbenannte Moodle-Aufgabe')} — {_format_due_date(deadline.get('due_date'))}"
            for deadline in sorted(past, key=_deadline_sort_key)
        )
    if upcoming:
        lines.extend(["", "Anstehend:"])
        lines.extend(
            f"- {deadline.get('name', 'Unbenannte Moodle-Aufgabe')} — {_format_due_date(deadline.get('due_date'))}"
            for deadline in sorted(upcoming, key=_deadline_sort_key)
        )
    return "\n".join(lines)


async def get_moodle_grades_context(
    course_id_or_course_name: str | int | None = None,
) -> str:
    """Return live Moodle grades for one course, or all courses when omitted."""
    courses = await _load_courses()
    if isinstance(courses, str):
        return courses
    if not courses:
        return "Keine Moodle-Kurse gefunden."

    explicit_course = _extract_explicit_course_reference(course_id_or_course_name)
    matched = _match_course(courses, explicit_course)
    selected_courses = [matched] if matched else courses
    sections: list[str] = []

    for course in selected_courses:
        if course is None:
            continue
        try:
            result = await moodle_service.get_moodle_course_grades(str(course.get("id")))
        except moodle_service.MoodleError as exc:
            sections.append(f"{course.get('fullname')}: Moodle-Noten konnten nicht geladen werden: {exc}")
            continue
        grades = result.get("grades", []) if isinstance(result, dict) else []
        if not grades:
            sections.append(f"{course.get('fullname')}: keine Moodle-Noten gefunden.")
            continue
        lines = [f"Moodle-Noten fuer {course.get('fullname') or course.get('shortname')}:"]
        for grade in grades:
            detail = []
            if grade.get("grade"):
                detail.append(f"Note: {grade.get('grade')}")
            if grade.get("percentage"):
                detail.append(str(grade.get("percentage")))
            if grade.get("feedback"):
                detail.append(f"Feedback: {grade.get('feedback')}")
            suffix = f" ({', '.join(detail)})" if detail else ""
            lines.append(f"- {grade.get('name', 'Unbenanntes Item')}{suffix}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "Keine Moodle-Noten gefunden."


async def get_moodle_materials_context(
    course_id_or_course_name: str | int | None = None,
) -> str:
    """Return live Moodle course materials and activities."""
    course = await _resolve_course(course_id_or_course_name)
    if isinstance(course, str):
        return course
    if course is None:
        return "Kein passender Moodle-Kurs gefunden. Bitte gib Kursname oder Course ID an."

    try:
        overview = await moodle_service.get_moodle_course_overview(str(course.get("id")))
    except moodle_service.MoodleError as exc:
        return f"Moodle-Materialien konnten nicht geladen werden: {exc}"
    if not overview:
        return f"Keine Moodle-Materialien fuer {course.get('fullname')} gefunden."

    lines = [f"Moodle-Materialien fuer {course.get('fullname') or course.get('shortname')}:"]
    for section in overview[:8]:
        section_name = section.get("section_name") or "Unbenannte Section"
        items = section.get("items", []) or []
        lines.append(f"- {section_name}: {len(items)} Item(s)")
        for item in items[:6]:
            item_name = item.get("name") or item.get("filename") or "Unbenanntes Item"
            extra = []
            if item.get("filename"):
                extra.append(str(item.get("filename")))
            if item.get("due_date"):
                extra.append(f"faellig { _format_due_date(item.get('due_date')) }")
            detail = f" ({', '.join(extra)})" if extra else ""
            lines.append(f"  - [{_item_type(item)}] {item_name}{detail}")
    return "\n".join(lines)


async def get_moodle_course_context(course_id_or_course_name: str | int) -> str:
    """Return a short course context: structure, materials, assignments and next deadline."""
    course = await _resolve_course(course_id_or_course_name)
    if isinstance(course, str):
        return course
    if course is None:
        return "Kein passender Moodle-Kurs gefunden. Bitte gib Kursname oder Course ID an."

    materials = await get_moodle_materials_context(course.get("id"))
    deadline = await get_next_moodle_deadline_context(course.get("id"))
    return (
        f"Moodle-Kurs: {course.get('fullname') or course.get('shortname')} "
        f"(Course ID: {course.get('id')})\n\n"
        f"{materials}\n\n{deadline}"
    )


async def get_moodle_context_for_message(message: str) -> str:
    """Route an explicit Moodle chat message to the right lightweight context helper."""
    text = (message or "").lower()
    if "grade" in text or "noten" in text or "note" in text:
        return await get_moodle_grades_context(message)
    if "deadline" in text or "aufgabe" in text or "abgabe" in text or "due" in text:
        wants_next = any(term in text for term in ("nächste", "naechste", "next"))
        if _extract_explicit_course_reference(message) and not wants_next:
            return await get_moodle_deadlines_context(message)
        return await get_next_moodle_deadline_context(message)
    if "overview" in text or "erklaer" in text or "erklär" in text or "kurs" in text and "moodle" in text:
        return await get_moodle_course_context(message)
    if "materials" in text or "materialien" in text or "files" in text or "dateien" in text:
        return await get_moodle_materials_context(message)
    return await get_moodle_courses_context(message)
