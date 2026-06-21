"""Moodle-API — belegte Kurse abrufen und Materialien on-demand in die RAG indizieren."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import moodle_service

router = APIRouter(prefix="/moodle", tags=["Moodle"])


class MoodleCourseOut(BaseModel):
    id: int
    fullname: str
    shortname: str
    semester: str


@router.get("/status")
async def moodle_status():
    """Ob ein Moodle-Token konfiguriert ist (für die UI)."""
    return {"configured": moodle_service.is_configured()}


@router.get("/courses", response_model=list[MoodleCourseOut])
async def moodle_courses():
    """Belegte Kurse, nach Semester sortiert (neueste zuerst)."""
    if not moodle_service.is_configured():
        raise HTTPException(status_code=503, detail="Kein Moodle-Token konfiguriert (MOODLE_TOKEN).")
    try:
        return await moodle_service.get_courses()
    except moodle_service.MoodleError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


class IndexCourseRequest(BaseModel):
    course_name: str
    chat_id: str | None = None
    user_id: str = "local"


@router.post("/index")
async def moodle_index_course(body: IndexCourseRequest):
    """Lädt die Materialien eines belegten Kurses und indiziert sie in die RAG-DB."""
    if not moodle_service.is_configured():
        raise HTTPException(status_code=503, detail="Kein Moodle-Token konfiguriert (MOODLE_TOKEN).")
    try:
        res = await moodle_service.index_course_by_name(body.course_name, body.chat_id, body.user_id)
    except moodle_service.MoodleError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if not res.get("matched"):
        raise HTTPException(status_code=404, detail=res.get("message", "Kein passender Kurs gefunden."))
    return res
