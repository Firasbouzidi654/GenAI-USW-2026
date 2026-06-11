import random
from datetime import date, time

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/moodle", tags=["Moodle Mock"])


class MoodleModule(BaseModel):
    id: int
    name: str
    semester: str
    lecturer: str
    credits: int


class MoodleGrade(BaseModel):
    module_id: int
    module_name: str
    grade: str | None
    credits: int
    status: str


class MoodleEvent(BaseModel):
    id: int
    module_id: int
    module_name: str
    title: str
    type: str
    date: date
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = None


MODULES = [
    MoodleModule(id=1, name="Datenbanken", semester="SoSe 2026", lecturer="Prof. Müller", credits=5),
    MoodleModule(id=2, name="Webtechnologien", semester="SoSe 2026", lecturer="Prof. Schmidt", credits=5),
    MoodleModule(id=3, name="Künstliche Intelligenz", semester="SoSe 2026", lecturer="Prof. Weber", credits=6),
]

def generate_mock_grades() -> list[MoodleGrade]:
    possible_grades = [
        "1.0",
        "1.3",
        "1.7",
        "2.0",
        "2.3",
        "2.7",
        "3.0",
    ]

    grades = []

    for module in MODULES:
        grades.append(
            MoodleGrade(
                module_id=module.id,
                module_name=module.name,
                grade=random.choice(possible_grades),
                credits=module.credits,
                status="bestanden",
            )
        )

    return grades

EVENTS = [
    MoodleEvent(
        id=1,
        module_id=1,
        module_name="Datenbanken",
        title="Datenbanken Vorlesung",
        type="LECTURE",
        date=date(2026, 6, 15),
        start_time=time(10, 0),
        end_time=time(11, 30),
        location="Raum A101",
    ),
    MoodleEvent(
        id=2,
        module_id=2,
        module_name="Webtechnologien",
        title="Frontend Abgabe",
        type="ASSIGNMENT",
        date=date(2026, 6, 20),
        location="Moodle",
    ),
    MoodleEvent(
        id=3,
        module_id=1,
        module_name="Datenbanken",
        title="Datenbanken Prüfung",
        type="EXAM",
        date=date(2026, 7, 10),
        start_time=time(9, 0),
        end_time=time(11, 0),
        location="Hörsaal 2",
    ),
]


@router.get("/modules", response_model=list[MoodleModule])
async def get_modules():
    return MODULES


@router.get("/grades", response_model=list[MoodleGrade])
async def get_grades():
    return generate_mock_grades()


@router.get("/events", response_model=list[MoodleEvent])
async def get_events():
    return EVENTS


@router.get("/exams", response_model=list[MoodleEvent])
async def get_exams():
    return [event for event in EVENTS if event.type == "EXAM"]