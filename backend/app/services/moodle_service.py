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
import logging
from datetime import datetime, timezone

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


async def get_courses() -> list[dict]:
    """Belegte Kurse des Token-Nutzers, sortiert nach Semester (neueste zuerst)."""
    info = await get_site_info()
    user_id = info.get("userid")
    if not user_id:
        raise MoodleError("Konnte die Moodle-User-ID nicht ermitteln.")

    raw = await _call("core_enrol_get_users_courses", userid=user_id)
    courses = []
    for c in raw if isinstance(raw, list) else []:
        start = c.get("startdate")
        courses.append({
            "id": c.get("id"),
            "shortname": c.get("shortname") or "",
            "fullname": c.get("fullname") or c.get("displayname") or "",
            "semester": _semester_from_timestamp(start),
            "startdate": start or 0,
        })
    courses.sort(key=lambda c: c["startdate"], reverse=True)
    return courses


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
