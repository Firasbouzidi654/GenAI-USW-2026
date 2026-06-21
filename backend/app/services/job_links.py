"""Job-Deep-Links — baut vorgefilterte Such-URLs für LinkedIn, StepStone und Indeed.

Nutzt die URL-Parameter-Filterung der Portale (keine API, kein Login, kein Scraping):
ein Klick öffnet die jeweilige Jobsuche bereits gefiltert nach Rolle, Ort, Erfahrungs-
niveau und Arbeitsform. Das ist die ToS-konforme Variante, um LinkedIn & Co. zu nutzen.
"""

from __future__ import annotations

from urllib.parse import quote, quote_plus

# LinkedIn-Erfahrungsniveau (f_E): 1=Praktikum, 2=Berufseinsteiger, 3=Associate, 4=Berufserfahren
_LINKEDIN_EXPERIENCE = {"internship": "1", "entry": "2", "associate": "3", "senior": "4"}
# LinkedIn-Arbeitsform (f_WT): 1=Vor Ort, 2=Remote, 3=Hybrid
_LINKEDIN_REMOTE = "2"


def build_job_links(
    keywords: str,
    location: str = "Berlin",
    experience: str = "entry",
    remote: bool = False,
    student: bool = True,
) -> list[dict]:
    """Liefert eine Liste {portal, url} mit vorgefilterten Such-Links.

    student=True stellt jeder Suche „Werkstudent" voran, sodass nur
    Werkstudentenstellen angezeigt werden.
    """
    kw = (keywords or "").strip()
    if not kw:
        return []

    # Im Studierenden-Modus die Suche auf Werkstudent fokussieren
    search_kw = f"Werkstudent {kw}" if student else kw

    links: list[dict] = []

    # ── LinkedIn (URL-Parameter-Filterung) ──
    li = (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={quote_plus(search_kw)}&location={quote_plus(location)}"
        f"&f_E={_LINKEDIN_EXPERIENCE.get(experience, '2')}"
    )
    if remote:
        li += f"&f_WT={_LINKEDIN_REMOTE}"
    links.append({"portal": "LinkedIn", "url": li})

    # ── StepStone (Pfad-basierte Suche) ──
    kw_slug = search_kw.lower().replace("/", " ").replace(" ", "-")
    loc_slug = location.lower().replace(" ", "-").split(",")[0]
    links.append({
        "portal": "StepStone",
        "url": f"https://www.stepstone.de/jobs/{quote(kw_slug)}/in-{quote(loc_slug)}?radius=30",
    })

    # ── Indeed Deutschland ──
    links.append({
        "portal": "Indeed",
        "url": f"https://de.indeed.com/jobs?q={quote_plus(search_kw)}&l={quote_plus(location)}",
    })

    return links
