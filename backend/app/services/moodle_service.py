"""Moodle-Web-Services-Client für die HTW Berlin.

Greift mit einem persönlichen Token direkt auf die Moodle-REST-API zu
(`/webservice/rest/server.php`). Ermöglicht den lazy/on-demand-Ansatz:
belegte Kurse auflisten und bei Bedarf die Materialien eines Kurses
herunterladen und in die RAG-Vektor-DB indizieren.

Token: in Moodle unter „Einstellungen → Sicherheitsschlüssel" erstellen und als
MOODLE_TOKEN in backend/.env hinterlegen.
"""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0
# Dateiendungen, die wir als Lernmaterial indizieren
_INDEXABLE_EXT = (".pdf",)


class MoodleError(RuntimeError):
    """Fehler bei einem Moodle-API-Aufruf (kein Token, ungültiger Token, Netzwerk …)."""


def is_configured() -> bool:
    return bool(settings.moodle_token)


async def _call(wsfunction: str, **params) -> dict | list:
    """Ruft eine Moodle-Webservice-Funktion auf und gibt das JSON zurück."""
    if not settings.moodle_token:
        raise MoodleError("Kein Moodle-Token konfiguriert (MOODLE_TOKEN in backend/.env).")

    url = f"{settings.moodle_url.rstrip('/')}/webservice/rest/server.php"
    data = {
        "wstoken": settings.moodle_token,
        "wsfunction": wsfunction,
        "moodlewsrestformat": "json",
        **params,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        raise MoodleError(f"Moodle nicht erreichbar: {exc}") from exc

    # Moodle meldet Fehler als JSON-Objekt mit 'exception'/'errorcode'
    if isinstance(payload, dict) and payload.get("exception"):
        raise MoodleError(payload.get("message") or payload.get("errorcode") or "Moodle-Fehler")
    return payload


def _semester_from_timestamp(ts: int | None) -> str:
    if not ts:
        return "Unbekanntes Semester"
    d = datetime.fromtimestamp(ts, tz=timezone.utc)
    # SoSe grob April–September, sonst WiSe
    if 3 <= d.month <= 8:
        return f"SoSe {d.year}"
    year = d.year if d.month >= 9 else d.year - 1
    return f"WiSe {year}/{str(year + 1)[2:]}"


async def get_site_info() -> dict:
    """core_webservice_get_site_info — liefert u.a. userid + erlaubte Funktionen."""
    return await _call("core_webservice_get_site_info")


async def get_moodle_user_id() -> int:
    if settings.moodle_user_id:
        try:
            return int(settings.moodle_user_id)
        except ValueError as exc:
            raise MoodleError("MOODLE_USER_ID muss eine Zahl sein.") from exc
    info = await get_site_info()
    user_id = info.get("userid")
    if not user_id:
        raise MoodleError("Konnte die Moodle-User-ID nicht ermitteln.")
    return int(user_id)


async def get_moodle_course_content(course_id: str) -> dict | list:
    """core_course_get_contents: liefert Abschnitte und Module eines Moodle-Kurses."""
    course_id = str(course_id).strip()
    if not course_id:
        raise MoodleError("Keine Moodle-Course-ID angegeben.")
    if not settings.moodle_token:
        raise MoodleError("Kein Moodle-Token konfiguriert (MOODLE_TOKEN in backend/.env).")

    url = f"{settings.moodle_url.rstrip('/')}/webservice/rest/server.php"
    params = {
        "wstoken": settings.moodle_token,
        "wsfunction": "core_course_get_contents",
        "moodlewsrestformat": "json",
        "courseid": course_id,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        raise MoodleError(f"Moodle nicht erreichbar: {exc}") from exc
    except ValueError as exc:
        raise MoodleError("Moodle hat keine gueltige JSON-Antwort geliefert.") from exc

    if isinstance(payload, dict) and payload.get("exception"):
        raise MoodleError(payload.get("message") or payload.get("errorcode") or "Moodle-Fehler")
    return payload


def _timestamp_to_iso(value) -> str | None:
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _extract_due_date(module: dict) -> str | None:
    for key in ("duedate", "due_date", "timedue", "deadline"):
        due = _timestamp_to_iso(module.get(key))
        if due:
            return due

    for entry in module.get("dates", []) or []:
        label = str(entry.get("label") or entry.get("name") or "").lower()
        if any(word in label for word in ("due", "abgabe", "fällig", "faellig", "deadline")):
            due = _timestamp_to_iso(entry.get("timestamp"))
            if due:
                return due

    customdata = module.get("customdata")
    if isinstance(customdata, str) and customdata.strip():
        try:
            parsed = json.loads(customdata)
        except ValueError:
            parsed = {}
        if isinstance(parsed, dict):
            for key in ("duedate", "due_date", "timedue", "deadline"):
                due = _timestamp_to_iso(parsed.get(key))
                if due:
                    return due
    return None


def _item_type(module: dict, content: dict | None = None) -> str:
    modname = module.get("modname") or ""
    if modname == "assign":
        return "assignment"
    if modname == "url":
        return "url"
    if content and content.get("type") == "file":
        return "file"
    return modname or "activity"


def _module_url(module: dict, content: dict | None = None) -> str | None:
    if content and content.get("fileurl"):
        return content.get("fileurl")
    return module.get("url")


def add_token_to_url(url: str, token: str) -> str:
    """Append Moodle's file token to a pluginfile URL."""
    if not url or not token:
        return url
    separator = "&" if "?" in url else "?"
    if url.endswith("?") or url.endswith("&"):
        separator = ""
    return f"{url}{separator}token={quote(token, safe='')}"


def _overview_item(module: dict, content: dict | None = None) -> dict:
    item = {
        "name": module.get("name") or (content or {}).get("filename") or "Untitled",
        "type": _item_type(module, content),
        "modname": module.get("modname") or "",
    }
    url = _module_url(module, content)
    if url:
        item["url" if item["type"] != "file" else "fileurl"] = url
        if item["type"] == "file":
            item["open_url"] = add_token_to_url(url, settings.moodle_token)
    if content:
        for key in ("filename", "mimetype", "filesize"):
            if content.get(key) is not None:
                item[key] = content.get(key)
    due_date = _extract_due_date(module)
    if due_date:
        item["due_date"] = due_date
    return item


async def get_moodle_course_overview(course_id: str) -> list[dict]:
    """Vereinfacht core_course_get_contents zu Sections mit Dateien, Links und Aufgaben."""
    raw = await get_moodle_course_content(course_id)
    sections: list[dict] = []
    for section in raw if isinstance(raw, list) else []:
        items: list[dict] = []
        for module in section.get("modules", []) or []:
            contents = module.get("contents", []) or []
            file_contents = [c for c in contents if c.get("type") == "file"]
            if file_contents:
                items.extend(_overview_item(module, content) for content in file_contents)
            else:
                items.append(_overview_item(module))
        sections.append({
            "section_name": section.get("name") or section.get("summary") or "Untitled section",
            "items": items,
        })
    return sections


def _deadline_status(module: dict, due_date: str | None) -> str:
    if module.get("completiondata", {}).get("state") == 1:
        return "done"
    if module.get("availability"):
        return "restricted"
    return "open" if due_date else "unknown"


def _deadline_item(course_id: str, section_name: str, module: dict) -> dict | None:
    if module.get("modname") != "assign":
        return None
    due_date = _extract_due_date(module)
    url = module.get("url")
    item = {
        "name": module.get("name") or "Assignment",
        "type": "assignment",
        "course_id": int(course_id) if str(course_id).isdigit() else course_id,
        "section_name": section_name,
        "due_date": due_date,
        "status": _deadline_status(module, due_date),
    }
    if url:
        item["url"] = url
        item["open_url"] = url
    return item


async def get_moodle_course_deadlines(course_id: str) -> dict:
    """Extrahiert Moodle-Deadlines aus Assignment-Modulen eines Kurses."""
    course_id = str(course_id).strip()
    if not course_id:
        raise MoodleError("Keine Moodle-Course-ID angegeben.")
    raw = await get_moodle_course_content(course_id)
    deadlines: list[dict] = []
    for section in raw if isinstance(raw, list) else []:
        section_name = section.get("name") or section.get("summary") or "Untitled section"
        for module in section.get("modules", []) or []:
            item = _deadline_item(course_id, section_name, module)
            if item:
                deadlines.append(item)

    deadlines.sort(key=lambda d: (d.get("due_date") is None, d.get("due_date") or ""))
    return {
        "course_id": int(course_id) if course_id.isdigit() else course_id,
        "deadlines": deadlines,
    }


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _grade_item(raw: dict) -> dict | None:
    name = _clean_text(raw.get("itemname") or raw.get("name") or raw.get("itemmodule"))
    if not name:
        return None
    return {
        "name": name,
        "type": _clean_text(raw.get("itemmodule") or raw.get("itemtype") or raw.get("type")),
        "grade": _clean_text(raw.get("gradeformatted") or raw.get("graderaw") or raw.get("grade")),
        "max_grade": _clean_text(raw.get("grademaxformatted") or raw.get("grademax") or raw.get("max_grade")),
        "percentage": _clean_text(raw.get("percentageformatted") or raw.get("percentage")),
        "feedback": _clean_text(raw.get("feedback") or raw.get("feedbackformatted")),
    }


async def get_moodle_course_grades(course_id: str) -> dict:
    """gradereport_user_get_grade_items: vereinfachte Noten fuer einen Moodle-Kurs."""
    course_id = str(course_id).strip()
    if not course_id:
        raise MoodleError("Keine Moodle-Course-ID angegeben.")
    user_id = await get_moodle_user_id()
    raw = await _call("gradereport_user_get_grade_items", courseid=course_id, userid=user_id)

    grades: list[dict] = []
    usergrades = raw.get("usergrades", []) if isinstance(raw, dict) else []
    for usergrade in usergrades if isinstance(usergrades, list) else []:
        for item in usergrade.get("gradeitems", []) or []:
            parsed = _grade_item(item)
            if parsed:
                grades.append(parsed)

    return {"course_id": int(course_id) if course_id.isdigit() else course_id, "grades": grades}


async def get_moodle_courses() -> list[dict]:
    """Belegte Moodle-Kurse des konfigurierten Nutzers."""
    user_id = await get_moodle_user_id()
    raw = await _call("core_enrol_get_users_courses", userid=user_id)
    courses = []
    for c in raw if isinstance(raw, list) else []:
        start = c.get("startdate")
        courses.append({
            "id": c.get("id"),
            "shortname": c.get("shortname") or "",
            "fullname": c.get("fullname") or c.get("displayname") or "",
            "visible": bool(c.get("visible", True)),
            "semester": _semester_from_timestamp(start),
            "startdate": start or 0,
        })
    courses.sort(key=lambda c: c["startdate"], reverse=True)
    return courses


async def get_courses() -> list[dict]:
    """Backward-compatible alias for existing Moodle integrations."""
    return await get_moodle_courses()


async def get_course_files(course_id: int) -> list[dict]:
    """Listet die indizierbaren Dateien (PDFs) eines Kurses mit Download-URL."""
    sections = await _call("core_course_get_contents", courseid=course_id)
    files: list[dict] = []
    for section in sections if isinstance(sections, list) else []:
        for module in section.get("modules", []):
            for content in module.get("contents", []) or []:
                if content.get("type") != "file":
                    continue
                fname = content.get("filename") or ""
                if not fname.lower().endswith(_INDEXABLE_EXT):
                    continue
                fileurl = content.get("fileurl")
                if not fileurl:
                    continue
                files.append({
                    "filename": fname,
                    "fileurl": fileurl,
                    "module": module.get("name") or "",
                    "section": section.get("name") or "",
                })
    return files


async def download_file_text(fileurl: str) -> str:
    """Lädt eine Datei (mit Token) herunter und extrahiert den Text (nur PDF)."""
    sep = "&" if "?" in fileurl else "?"
    url = f"{fileurl}{sep}token={settings.moodle_token}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content
    except httpx.HTTPError as exc:
        raise MoodleError(f"Datei-Download fehlgeschlagen: {exc}") from exc

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception as exc:
        logger.warning("PDF aus Moodle nicht lesbar: %s", exc)
        return ""


def _match_course(courses: list[dict], name: str) -> dict | None:
    """Findet den am besten passenden Kurs zu einem (Teil-)Namen (case-insensitive)."""
    q = (name or "").strip().lower()
    if not q:
        return None
    # 1. exakte/enthaltene Übereinstimmung im Voll- oder Kurznamen
    for c in courses:
        if q in c["fullname"].lower() or q in c["shortname"].lower():
            return c
    # 2. Wort-Überlappung
    q_words = set(q.split())
    best, best_overlap = None, 0
    for c in courses:
        words = set((c["fullname"] + " " + c["shortname"]).lower().split())
        overlap = len(q_words & words)
        if overlap > best_overlap:
            best, best_overlap = c, overlap
    return best if best_overlap else None


async def index_course_by_name(
    name: str, chat_id: str | None, user_id: str = "local", max_files: int = 15
) -> dict:
    """Findet den belegten Kurs zu ``name``, lädt dessen PDFs und indiziert sie in die RAG-DB.

    Returns ein Dict mit Status/Ergebnis (matched_course, files_indexed, chunks).
    """
    import asyncio

    from app.rag.pipeline import index_text

    courses = await get_courses()
    course = _match_course(courses, name)
    if course is None:
        return {
            "matched": False,
            "message": f"Kein belegter Kurs passt zu '{name}'.",
            "available": [c["fullname"] for c in courses],
        }

    files = await get_course_files(course["id"])
    indexed, chunks = 0, 0
    for f in files[:max_files]:
        try:
            text = await download_file_text(f["fileurl"])
        except MoodleError:
            continue
        if not text:
            continue
        n = await asyncio.to_thread(
            index_text, f["filename"], text, chat_id, user_id,
            {"course_id": course["id"], "course_name": course["fullname"], "moodle": "1"},
        )
        if n:
            indexed += 1
            chunks += n

    return {
        "matched": True,
        "course": course["fullname"],
        "semester": course["semester"],
        "files_found": len(files),
        "files_indexed": indexed,
        "chunks": chunks,
    }
