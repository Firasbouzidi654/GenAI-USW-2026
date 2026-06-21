"""Curriculum-API — Modulhandbuch hochladen und den Vorgänger-Graph abrufen."""

import io
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.models.curriculum import CurriculumModule
from app.services.curriculum_service import extract_and_store, suggest_module

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/curriculum", tags=["Curriculum"])

# Einfacher In-Memory-Status (Single-User-Betrieb)
_state = {"processing": False, "with_prerequisites": 0}


class ModuleOut(BaseModel):
    name: str
    description: str | None = None
    semester: str | None = None
    prerequisites: list[str] = []
    competencies: list[str] = []

    model_config = {"from_attributes": True}


class StatusOut(BaseModel):
    processing: bool
    modules: int
    with_prerequisites: int


async def _run_extraction(text: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            result = await extract_and_store(text, db)
            _state["with_prerequisites"] = result.get("with_prerequisites", 0)
            logger.info("Curriculum extrahiert: %s", result)
    except Exception as exc:
        logger.error("Curriculum-Extraktion fehlgeschlagen: %s", exc)
    finally:
        _state["processing"] = False


@router.get("/status", response_model=StatusOut)
async def curriculum_status(db: AsyncSession = Depends(get_db)):
    try:
        count = (await db.execute(select(func.count()).select_from(CurriculumModule))).scalar() or 0
    except Exception:
        count = 0
    return StatusOut(processing=_state["processing"], modules=count, with_prerequisites=_state["with_prerequisites"])


@router.get("", response_model=list[ModuleOut])
async def list_curriculum(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CurriculumModule).order_by(CurriculumModule.name))
    return result.scalars().all()


@router.post("/upload")
async def upload_curriculum(file: UploadFile, background_tasks: BackgroundTasks):
    """Lädt das Modulhandbuch (PDF) hoch und extrahiert im Hintergrund den Vorgänger-Graph."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt.")

    contents = await file.read()
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(contents))
        text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception:
        raise HTTPException(status_code=422, detail="PDF konnte nicht gelesen werden.")

    if not text:
        raise HTTPException(status_code=422, detail="Im PDF wurde kein Text gefunden (evtl. gescannt?).")

    _state["processing"] = True
    _state["with_prerequisites"] = 0
    background_tasks.add_task(_run_extraction, text)
    return {"status": "processing", "message": "Modulhandbuch wird analysiert — das dauert einen Moment."}


class SuggestModuleRequest(BaseModel):
    documents: list[str] = []
    user_id: str = "local"


class SuggestModuleResponse(BaseModel):
    module: str | None = None


@router.post("/suggest-module", response_model=SuggestModuleResponse)
async def suggest_module_endpoint(body: SuggestModuleRequest, db: AsyncSession = Depends(get_db)):
    """Ermittelt anhand der gewählten Dokumente das passende Modul aus dem Modulhandbuch."""
    if not body.documents:
        return SuggestModuleResponse(module=None)
    try:
        name = await suggest_module(body.documents, db, body.user_id)
    except Exception:
        name = None
    return SuggestModuleResponse(module=name)


@router.delete("", status_code=204)
async def delete_curriculum(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete as sa_delete
    try:
        await db.execute(sa_delete(CurriculumModule))
        await db.commit()
        _state["with_prerequisites"] = 0
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Curriculum konnte nicht gelöscht werden.")
