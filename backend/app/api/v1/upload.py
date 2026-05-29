import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.rag.pipeline import process_document

UPLOAD_DIR = Path("uploads")

router = APIRouter()


@router.post("/upload")
async def upload_pdf(file: UploadFile):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt.")

    UPLOAD_DIR.mkdir(exist_ok=True)
    dest = UPLOAD_DIR / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    await process_document(str(dest))

    return {"status": "ok", "filename": file.filename}