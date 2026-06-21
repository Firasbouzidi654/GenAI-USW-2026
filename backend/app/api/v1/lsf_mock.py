"""LSF-Mock — bildet das LSF-System der HTW Berlin nach.

Stellt die zentrale Datenquelle der App bereit: Module, Noten und Termine.
Die Daten orientieren sich an einer echten HTW-Notenbescheinigung
(Wirtschaftsinformatik B.Sc.) und einem echten LSF-Stundenplan-Export (SoSe 2026).

Termine werden relativ zum heutigen Datum generiert, damit Kalender und Planner
immer aktuelle, bevorstehende Einträge enthalten. Die Daten werden über den
Sync-Service (`app/services/lsf_sync.py`) in die DB-Tabellen übernommen.
"""

from __future__ import annotations

from datetime import date, time, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/lsf", tags=["LSF Mock"])

STUDENT_NAME = "Erika Musterfrau"
MATRIKELNUMMER = "123456"
STUDIENGANG = "Wirtschaftsinformatik (Bachelor)"
CURRENT_SEMESTER = "SoSe 2026"


# ── Schemas ──────────────────────────────────────────────────────────────────

class LsfGrade(BaseModel):
    module_name: str
    semester: str
    grade: str | None
    ects: int
    type: str  # PF | WP
    status: str


class LsfTermin(BaseModel):
    id: str
    module_name: str
    title: str
    type: str  # LECTURE | EXERCISE | EXAM | ASSIGNMENT | PRESENTATION
    date: date
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = None
    lecturer: str | None = None
    description: str | None = None


# ── Noten (aus der Prüfungsbescheinigung) ────────────────────────────────────
# (Modulname, Semester, Note, ECTS, PF/WP, Status)
_GRADES: list[tuple[str, str, str | None, int, str, str]] = [
    ("Einführung in die BWL und VWL", "SS24", "1.0", 5, "PF", "bestanden"),
    ("Unternehmens- und Personalmanagement", "WS24/25", "1.0", 5, "PF", "bestanden"),
    ("Investition und Finanzierung", "WS25/26", "2.0", 5, "PF", "bestanden"),
    ("Buchführung und Bilanzen", "WS24/25", "1.0", 5, "PF", "bestanden"),
    ("Controlling", "SS25", "1.0", 5, "PF", "bestanden"),
    ("Mathematik", "SS24", "2.3", 5, "PF", "bestanden"),
    ("Statistik", "SS25", "1.3", 5, "PF", "bestanden"),
    ("Einführung in die Wirtschaftsinformatik", "SS24", "3.0", 5, "PF", "bestanden"),
    ("Geschäftsprozesse und betriebliche Anwendungen", "WS24/25", "1.0", 5, "PF", "bestanden"),
    ("Grundlagen Projektmanagement", "WS24/25", "1.3", 5, "PF", "bestanden"),
    ("Datenmodellierung und Datenbanksysteme", "WS24/25", "1.7", 5, "PF", "bestanden"),
    ("Datenbanktechnologien", "SS25", "2.7", 5, "PF", "bestanden"),
    ("Grundlagen der Programmierung", "SS24", "2.7", 5, "PF", "bestanden"),
    ("Angewandte Programmierung", "WS24/25", "1.3", 5, "PF", "bestanden"),
    ("Grundlagen des Software-Engineering", "SS24", "1.3", 5, "PF", "bestanden"),
    ("Modellierung von Anwendungssystemen", "SS25", "1.3", 6, "PF", "bestanden"),
    ("Rechnernetze", "SS24", "2.0", 5, "PF", "anerkannt"),
    ("Webtechnologien", "SS25", "1.0", 5, "PF", "bestanden"),
    ("Fachpraktikum", "WS25/26", None, 20, "PF", "mit Erfolg"),
    ("Präsentation und Moderation", "WS25/26", "1.3", 5, "WP", "bestanden"),
    ("Englisch, Mittelstufe 2/Wirtschaft (GER B2.1)", "SS25", "1.0", 4, "WP", "anerkannt"),
]


def get_grades() -> list[LsfGrade]:
    return [
        LsfGrade(module_name=n, semester=s, grade=g, ects=e, type=t, status=st)
        for (n, s, g, e, t, st) in _GRADES
    ]


# ── Stundenplan SoSe 2026 (aus LSF_Plan.ics) ─────────────────────────────────
# (Modulname, Wochentag 0=Mo … 4=Fr, start, ende, typ, raum, dozent)
_WEEKLY_TIMETABLE = [
    ("Produktionswirtschaft/Logistik", 0, time(9, 45), time(11, 15), "LECTURE", "TA Gebäude A 146", "Fleschutz-Balarezo"),
    ("Unternehmenssoftware", 1, time(8, 0), time(9, 45), "LECTURE", "TA Gebäude A 236", "Hochstein"),
    ("Unternehmenssoftware", 1, time(9, 45), time(11, 15), "EXERCISE", "TA Gebäude A 236", "Hochstein"),
    ("Statistik", 1, time(12, 0), time(13, 30), "LECTURE", "TA Gebäude A 146", "Spott"),
    ("Informationssicherheit", 1, time(12, 0), time(15, 15), "EXERCISE", "WH Gebäude G 119", "Tunca, Breu"),
    ("Statistik", 2, time(9, 45), time(11, 15), "EXERCISE", "TA Gebäude A 013", "Spott"),
    ("Marketing", 2, time(13, 45), time(17, 0), "EXERCISE", "TA Gebäude A 029", "Becker"),
    ("Produktionswirtschaft/Logistik", 2, time(17, 15), time(18, 45), "EXERCISE", "TA Gebäude A 143", "Schleinitz"),
    ("Management English", 3, time(8, 0), time(11, 15), "EXERCISE", "TA Gebäude A 127", "Skiba"),
    ("Verteilte Anwendungen", 3, time(12, 0), time(13, 30), "LECTURE", "TA Gebäude A 029", "Flachs, Stanik"),
    ("Verteilte Anwendungen", 3, time(13, 45), time(15, 15), "EXERCISE", "TA Gebäude A 143", "Flachs, Stanik"),
]

# Prüfungen / Abgaben / Präsentationen relativ zu heute:
# (Modulname, tage-offset, titel, typ, start, ende, raum, beschreibung)
_ONE_OFF_TERMINE = [
    ("Informationssicherheit", 5, "Übungsabgabe Informationssicherheit", "ASSIGNMENT", None, None, "Moodle", "Abgabe Übungsblatt"),
    ("Verteilte Anwendungen", 9, "Projektabgabe Verteilte Anwendungen", "ASSIGNMENT", None, None, "Moodle", "Abgabe des Microservice-Projekts"),
    ("Marketing", 12, "Präsentation Marketing-Konzept", "PRESENTATION", time(13, 45), time(15, 0), "TA Gebäude A", "Gruppenpräsentation"),
    ("Produktionswirtschaft/Logistik", 28, "Klausur Produktionswirtschaft/Logistik", "EXAM", time(9, 0), time(11, 0), "TA Gebäude A 146", "Schriftliche Prüfung"),
    ("Unternehmenssoftware", 31, "Klausur Unternehmenssoftware", "EXAM", time(8, 0), time(10, 0), "TA Gebäude A 236", "Schriftliche Prüfung"),
    ("Statistik", 34, "Klausur Statistik", "EXAM", time(12, 0), time(14, 0), "TA Gebäude A 146", "Schriftliche Prüfung"),
    ("Verteilte Anwendungen", 37, "Klausur Verteilte Anwendungen", "EXAM", time(12, 0), time(13, 30), "TA Gebäude A", "Schriftliche Prüfung"),
]

_LECTURE_HORIZON_DAYS = 21

_TYPE_LABEL = {"LECTURE": "Vorlesung", "EXERCISE": "Übung"}


def get_termine(today: date | None = None) -> list[LsfTermin]:
    """Erzeugt alle Termine relativ zu ``today`` (Standard: heute)."""
    today = today or date.today()
    termine: list[LsfTermin] = []

    # Wöchentliche Vorlesungen/Übungen für den Horizont expandieren
    for offset in range(_LECTURE_HORIZON_DAYS):
        day = today + timedelta(days=offset)
        for name, weekday, start, end, ttype, room, lecturer in _WEEKLY_TIMETABLE:
            if day.weekday() != weekday:
                continue
            termine.append(LsfTermin(
                id=f"{name}-{ttype}-{day.isoformat()}-{start.strftime('%H%M')}",
                module_name=name,
                title=f"{name} ({_TYPE_LABEL.get(ttype, ttype)})",
                type=ttype,
                date=day,
                start_time=start,
                end_time=end,
                location=room,
                lecturer=lecturer,
            ))

    # Einmalige Termine (Abgaben, Präsentationen, Prüfungen)
    for name, day_offset, title, ttype, start, end, room, desc in _ONE_OFF_TERMINE:
        day = today + timedelta(days=day_offset)
        termine.append(LsfTermin(
            id=f"{name}-{ttype}-{day.isoformat()}",
            module_name=name,
            title=title,
            type=ttype,
            date=day,
            start_time=start,
            end_time=end,
            location=room,
            description=desc,
        ))

    termine.sort(key=lambda t: (t.date, t.start_time or time(0, 0)))
    return termine


# ── Endpunkte ────────────────────────────────────────────────────────────────

@router.get("/grades", response_model=list[LsfGrade])
async def lsf_grades():
    """Noten der abgeschlossenen Module (Prüfungsbescheinigung)."""
    return get_grades()


@router.get("/termine", response_model=list[LsfTermin])
async def lsf_termine():
    """Alle bevorstehenden Termine (Vorlesungen, Übungen, Prüfungen, Abgaben, Präsentationen)."""
    return get_termine()


@router.get("/exams", response_model=list[LsfTermin])
async def lsf_exams():
    """Nur Prüfungstermine."""
    return [t for t in get_termine() if t.type == "EXAM"]


@router.get("/profile")
async def lsf_profile():
    """Stammdaten des Studierenden."""
    return {
        "student_name": STUDENT_NAME,
        "matrikelnummer": MATRIKELNUMMER,
        "studiengang": STUDIENGANG,
        "semester": CURRENT_SEMESTER,
    }


@router.post("/sync")
async def lsf_sync(db: AsyncSession = Depends(get_db)):
    """Synchronisiert die LSF-Daten in die Datenbank (Noten, Kalender, Planner, Prüfungen).

    Idempotent: bestehende LSF-Daten werden ersetzt.
    """
    from app.services.lsf_sync import sync_lsf_to_db

    return await sync_lsf_to_db(db)
