import httpx
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()

_N8N_WEBHOOK = "http://localhost:5678/webhook/grades/extract"
_TIMEOUT = 60.0


class CourseResult(BaseModel):
    courseName: str
    semester: str | None = None
    grade: str | None = None
    credits: int | None = None


class GradesResponse(BaseModel):
    studentName: str | None = None
    totalCredits: int | None = None
    courses: list[CourseResult]


@router.post("/grades/upload", response_model=GradesResponse)
async def upload_grades_pdf(file: UploadFile):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt.")

    contents = await file.read()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            n8n_response = await client.post(
                _N8N_WEBHOOK,
                files={"file": (file.filename, contents, "application/pdf")},
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="n8n-Webhook Timeout: Verarbeitung hat zu lange gedauert.",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="n8n-Webhook nicht erreichbar (localhost:5678).",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Fehler beim Senden an den n8n-Webhook.",
        )

    if n8n_response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"n8n-Webhook antwortete mit Status {n8n_response.status_code}.",
        )

    try:
        data = n8n_response.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Ungültige JSON-Antwort vom n8n-Webhook.",
        )

    try:
        return GradesResponse(**data)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="n8n-Antwort entspricht nicht dem erwarteten Format (studentName, totalCredits, courses).",
        )
