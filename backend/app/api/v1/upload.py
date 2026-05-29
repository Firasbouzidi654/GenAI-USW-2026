import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.document import Document
from app.rag.pipeline import process_document

UPLOAD_DIR = Path("uploads")

router = APIRouter()


@router.post("/upload")
async def upload_pdf(file: UploadFile, db: AsyncSession = Depends(get_db)):
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

    await process_document(str(dest))

    try:
        db.add(Document(filename=filename))
        await db.commit()
    except Exception:
        pass

    return {"status": "ok", "filename": filename}