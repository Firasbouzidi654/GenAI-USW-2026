from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.language_progress import LanguageProgress
from app.services.language_tutor_service import (
    SUPPORTED_LANGUAGES,
    compute_progress_update,
    get_tutor_reply,
)

router = APIRouter()


class TutorTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class LanguageTutorRequest(BaseModel):
    language: str
    message: str = Field(..., min_length=1)
    history: list[TutorTurn] = []


class VocabItem(BaseModel):
    word: str
    meaning: str


class ProgressOut(BaseModel):
    language: str
    cefr_level: str
    xp: int


class LanguageTutorResponse(BaseModel):
    reply: str
    correction: str | None = None
    explanation: str | None = None
    vocabulary: list[VocabItem] = []
    better_version: str | None = None
    next_question: str | None = None
    progress: ProgressOut


_MAX_HISTORY_TURNS = 12


def _validate_language(language: str) -> None:
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=422,
            detail=f"language must be one of {sorted(SUPPORTED_LANGUAGES)}.",
        )


async def _get_or_create_progress(language: str, db: AsyncSession) -> LanguageProgress:
    result = await db.execute(select(LanguageProgress).where(LanguageProgress.language == language))
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = LanguageProgress(language=language)
        db.add(progress)
        await db.flush()
    return progress


@router.get("/ai/language-tutor/progress/{language}", response_model=ProgressOut)
async def get_language_progress(language: str, db: AsyncSession = Depends(get_db)):
    _validate_language(language)
    try:
        result = await db.execute(select(LanguageProgress).where(LanguageProgress.language == language))
        progress = result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    if progress is None:
        return ProgressOut(language=language, cefr_level="A1", xp=0)
    return ProgressOut(language=progress.language, cefr_level=progress.cefr_level, xp=progress.xp)


@router.post("/ai/language-tutor", response_model=LanguageTutorResponse)
async def language_tutor(body: LanguageTutorRequest, db: AsyncSession = Depends(get_db)):
    _validate_language(body.language)

    try:
        progress = await _get_or_create_progress(body.language, db)
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    history = [t.model_dump() for t in body.history[-_MAX_HISTORY_TURNS:]]

    try:
        result = await get_tutor_reply(body.language, body.message, history, cefr_level=progress.cefr_level)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    try:
        new_score, new_xp, new_level = compute_progress_update(
            current_score=progress.level_score,
            current_xp=progress.xp,
            estimated_cefr=result.get("estimated_cefr"),
            had_correction=bool(result.get("correction")),
        )
        progress.level_score = new_score
        progress.xp = new_xp
        progress.cefr_level = new_level
        progress.turn_count += 1
        await db.commit()
        await db.refresh(progress)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Fortschritt konnte nicht gespeichert werden.")

    return LanguageTutorResponse(
        reply=result["reply"],
        correction=result.get("correction"),
        explanation=result.get("explanation"),
        vocabulary=result.get("vocabulary", []),
        better_version=result.get("better_version"),
        next_question=result.get("next_question"),
        progress=ProgressOut(language=progress.language, cefr_level=progress.cefr_level, xp=progress.xp),
    )
