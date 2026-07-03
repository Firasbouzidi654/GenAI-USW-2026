"""Profil-Endpunkt — vollständiger Reset aller vom Nutzer erzeugten Daten."""

import logging
import shutil

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.attempt_answer import AttemptAnswer
from app.models.calendar_event import CalendarEvent
from app.models.curriculum import CurriculumModule
from app.models.document import Document
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_question import QuizQuestion
from app.models.resume import Resume
from app.api.v1.upload import UPLOAD_DIR
from app.rag.store import clear_collection

logger = logging.getLogger(__name__)

router = APIRouter()


def _clear_uploaded_files() -> bool:
    """Remove uploaded files from disk for the single-user reset flow."""
    if not UPLOAD_DIR.exists():
        return True
    try:
        for child in UPLOAD_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        return True
    except Exception as exc:
        logger.warning("Upload-Ordner konnte nicht vollständig geleert werden: %s", exc)
        return False


@router.post("/profile/reset")
async def reset_profile(db: AsyncSession = Depends(get_db)):
    """Löscht ALLE gespeicherten Nutzerdaten: Quizze, Versuche, Dokumente (inkl.
    Vektor-DB), Lebenslauf, Modulhandbuch und eigene Kalender-Termine.

    Nicht betroffen: die LSF-Mock-Daten (Noten/Stundenplan/Prüfungen), da diese
    jederzeit neu synchronisiert werden.
    """
    try:
        # Quiz-Daten (Reihenfolge wegen Fremdschlüsseln)
        await db.execute(delete(AttemptAnswer))
        await db.execute(delete(QuizAttempt))
        await db.execute(delete(QuizQuestion))
        await db.execute(delete(Quiz))
        # Dokumente, CV, Modulhandbuch, eigene Termine
        await db.execute(delete(Document))
        await db.execute(delete(Resume))
        await db.execute(delete(CurriculumModule))
        await db.execute(delete(CalendarEvent).where(CalendarEvent.source == "user"))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Profil-Reset fehlgeschlagen: %s", exc)
        raise HTTPException(status_code=503, detail="Zurücksetzen fehlgeschlagen.")

    # Vektor-DB und Upload-Ordner defensiv leeren. Fehler hier sollen den Reset
    # nicht scheitern lassen, werden aber im Response sichtbar.
    chroma_cleared = clear_collection()
    uploads_cleared = _clear_uploaded_files()

    return {"reset": True, "chroma_cleared": chroma_cleared, "uploads_cleared": uploads_cleared}
