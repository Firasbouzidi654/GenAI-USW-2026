"""Job-Deep-Links — baut vorgefilterte Such-URLs für LinkedIn, StepStone und Indeed.

Nutzt die URL-Parameter-Filterung der Portale (keine API, kein Login, kein Scraping):
ein Klick öffnet die jeweilige Jobsuche bereits gefiltert nach Rolle, Ort, Erfahrungs-
niveau und Arbeitsform. Das ist die ToS-konforme Variante, um LinkedIn & Co. zu nutzen.
"""

from __future__ import annotations

import re
from urllib.parse import quote, quote_plus

# LinkedIn-Erfahrungsniveau (f_E): 1=Praktikum, 2=Berufseinsteiger, 3=Associate, 4=Berufserfahren
_LINKEDIN_EXPERIENCE = {"internship": "1", "entry": "2", "associate": "3", "senior": "4"}
# LinkedIn-Arbeitsform (f_WT): 1=Vor Ort, 2=Remote, 3=Hybrid
_LINKEDIN_REMOTE = "2"

# Gender-Marker (z. B. „:in", „/-in", „(m/w/d)"), die einen Suchbegriff unbrauchbar machen
_GENDER_RE = re.compile(r"\(\s*m\s*/\s*w\s*/\s*[dx]\s*\)|[:/*]\s*in\b|/-in\b", re.IGNORECASE)
# Vorangestelltes „Werkstudent" / „Werkstudent:in" am Anfang
_WERKSTUDENT_RE = re.compile(r"^\s*werkstudent(?:[:/*]?-?in)?\s+", re.IGNORECASE)


def _clean_role(title: str) -> str:
    """Macht aus einem Rollentitel einen suchtauglichen Begriff:
    entfernt ein vorangestelltes „Werkstudent(:in)", Gender-Marker und nimmt bei
    Alternativen (Slash) nur die erste, primäre Rolle. So findet die Portalsuche
    tatsächlich Treffer statt einer überspezifischen 0-Treffer-Phrase.
    """
    t = (title or "").strip()
    t = _WERKSTUDENT_RE.sub("", t)
    # Erst Gender-Marker wie „(m/w/d)" / „:in" raus (enthalten selbst Slashes) …
    t = _GENDER_RE.sub("", t)
    # … dann bei echten Alternativen („Business Intelligence / Data Analytics")
    # nur die primäre Rolle nehmen.
    t = t.split("/")[0]
    return re.sub(r"\s{2,}", " ", t).strip(" -–·,")


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
    kw = _clean_role(keywords)
    if not kw:
        return []

    # Im Studierenden-Modus die Suche auf Werkstudent fokussieren (genau einmal,
    # _clean_role hat ein evtl. bereits enthaltenes „Werkstudent" entfernt)
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
