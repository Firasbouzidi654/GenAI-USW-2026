import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.grade import Grade

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


@router.get("/grades", response_model=GradesResponse)
async def get_grades(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Grade).order_by(Grade.semester, Grade.course_name))
        rows = result.scalars().all()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    student_name = next((r.student_name for r in rows if r.student_name), None)
    total_credits = sum(r.credits for r in rows if r.credits) or None
    return GradesResponse(
        studentName=student_name,
        totalCredits=total_credits,
        courses=[
            CourseResult(courseName=r.course_name, semester=r.semester, grade=r.grade, credits=r.credits)
            for r in rows
        ],
    )


@router.delete("/grades", status_code=204)
async def delete_all_grades(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(delete(Grade))
        await db.commit()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.post("/grades/upload", response_model=GradesResponse)
async def upload_grades_pdf(file: UploadFile, db: AsyncSession = Depends(get_db)):
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
        parsed = GradesResponse(**data)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="n8n-Antwort entspricht nicht dem erwarteten Format (studentName, totalCredits, courses).",
        )

    try:
        await db.execute(delete(Grade))
        db.add_all(
            [
                Grade(
                    student_name=parsed.studentName,
                    course_name=c.courseName,
                    semester=c.semester,
                    grade=c.grade,
                    credits=c.credits,
                )
                for c in parsed.courses
            ]
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    return parsed
