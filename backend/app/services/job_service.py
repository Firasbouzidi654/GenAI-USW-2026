"""Job-Service — echte Stellensuche über öffentliche Job-Portal-APIs.

Hintergrund: LinkedIn und StepStone bieten keine offen nutzbare Job-Such-API
(nur Partner-/Bezahlmodelle). Daher nutzt dieser Service:

  • Adzuna (https://developer.adzuna.com) — echte Suche inkl. Gehalt für Deutschland,
    benötigt einen kostenlosen app_id/app_key. Wird verwendet, wenn konfiguriert.
  • Arbeitnow (https://www.arbeitnow.com/api/job-board-api) — frei, ohne Key,
    deutsche/EU-Stellen. Fallback, lokal nach Stichwörtern gefiltert.

Alle Aufrufe sind tolerant: bei Fehlern wird eine leere Liste zurückgegeben.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0
_ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"

# Begriffe, die eine Werkstudentenstelle kennzeichnen (für striktes Filtern)
_STUDENT_TERMS = ("werkstudent", "working student", "studentische", "studierende", "studentenjob")


def _is_student_job(text: str) -> bool:
    t = (text or "").lower()
    return any(term in t for term in _STUDENT_TERMS)


def active_source() -> str:
    """Welche Quelle aktuell genutzt wird (für die UI)."""
    if settings.adzuna_app_id and settings.adzuna_app_key:
        return "Adzuna"
    return "Arbeitnow"


def _clean(text: str | None, limit: int = 240) -> str:
    if not text:
        return ""
    import re
    t = re.sub(r"<[^>]+>", " ", text)        # HTML-Tags entfernen
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


async def _search_adzuna(keywords: list[str], location: str, limit: int, student: bool) -> list[dict]:
    country = settings.adzuna_country or "de"
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "results_per_page": limit * 3 if student else limit,
        "what_or": " ".join(keywords[:4]),
        "where": location,
        "content-type": "application/json",
    }
    if student:
        # Erzwingt, dass "Werkstudent" im Treffer vorkommt
        params["what_and"] = "Werkstudent"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    jobs: list[dict] = []
    for r in data.get("results", []):
        if student and not _is_student_job(f"{r.get('title','')} {r.get('description','')}"):
            continue
        if len(jobs) >= limit:
            break
        salary = None
        smin, smax = r.get("salary_min"), r.get("salary_max")
        if smin and smax:
            salary = f"€{int(smin):,} – €{int(smax):,}".replace(",", ".")
        jobs.append({
            "title": r.get("title", "").strip(),
            "company": (r.get("company") or {}).get("display_name", "").strip(),
            "location": (r.get("location") or {}).get("display_name", "").strip(),
            "url": r.get("redirect_url", ""),
            "salary": salary,
            "remote": None,
            "description": _clean(r.get("description")),
            "source": "Adzuna",
        })
    return jobs


async def _search_arbeitnow(keywords: list[str], limit: int, student: bool) -> list[dict]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(_ARBEITNOW_URL)
        resp.raise_for_status()
        data = resp.json()

    terms = [k.lower() for k in keywords if k]
    scored: list[tuple[int, dict]] = []
    for r in data.get("data", []):
        title = r.get("title", "")
        tags = " ".join(r.get("tags", []) or [])
        jtypes = " ".join(r.get("job_types", []) or [])
        full = f"{title} {tags} {jtypes} {r.get('description','')[:600]}"

        # Im Studierenden-Modus NUR Werkstudentenstellen
        if student and not _is_student_job(full):
            continue

        haystack = full.lower()
        score = sum(1 for t in terms if t in haystack)
        # Werkstudent-Treffer auch ohne Themen-Match behalten (sind eh selten in der freien Quelle)
        if score == 0 and terms and not student:
            continue
        scored.append((score, {
            "title": title.strip(),
            "company": r.get("company_name", "").strip(),
            "location": r.get("location", "").strip(),
            "url": r.get("url", ""),
            "salary": None,
            "remote": bool(r.get("remote")),
            "description": _clean(r.get("description")),
            "source": "Arbeitnow",
        }))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [j for _, j in scored[:limit]]


async def search_jobs(
    keywords: list[str],
    location: str | None = None,
    limit: int = 8,
    student: bool | None = None,
) -> list[dict]:
    """Sucht echte Stellen zu den Stichwörtern. Gibt bei Fehlern [] zurück.

    student=True (Standard via Config) → es werden ausschließlich Werkstudentenstellen
    zurückgegeben.
    """
    keywords = [k for k in (keywords or []) if k and k.strip()]
    if not keywords:
        return []
    location = location or settings.job_location
    if student is None:
        student = settings.job_student_only

    try:
        if settings.adzuna_app_id and settings.adzuna_app_key:
            return await _search_adzuna(keywords, location, limit, student)
        return await _search_arbeitnow(keywords, limit, student)
    except Exception as exc:
        logger.warning("Stellensuche fehlgeschlagen (%s): %s", active_source(), exc)
        return []
