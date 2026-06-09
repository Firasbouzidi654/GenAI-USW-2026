import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.document import Document
from app.rag.pipeline import process_document_sync

UPLOAD_DIR = Path("uploads")

router = APIRouter()


@router.post("/upload")
async def upload_pdf(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt.")

    filename = Path(file.filename).name
    if not filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname.")

    UPLOAD_DIR.mkdir(exist_ok=True)
    dest = UPLOAD_DIR / filename

    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception:
        raise HTTPException(status_code=500, detail="Datei konnte nicht gespeichert werden.")

    # Record in DB immediately so the UI gets a fast response.
    try:
        db.add(Document(filename=filename))
        await db.commit()
    except Exception:
        pass

    # Embedding + ChromaDB indexing happens in a background thread —
    # the HTTP response is returned to the browser right away.
    background_tasks.add_task(process_document_sync, str(dest))

    return {"status": "ok", "filename": filename}


@router.get("/documents", response_model=list[str])
async def list_documents(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(Document.filename).order_by(Document.uploaded_at.desc())
        )
        return [row[0] for row in result.all()]
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")