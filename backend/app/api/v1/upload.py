import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.document import DEFAULT_USER_ID, Document
from app.rag.pipeline import process_document_sync
from app.rag.store import get_collection

UPLOAD_DIR = Path("uploads")

router = APIRouter()


@router.post("/upload")
async def upload_pdf(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    chat_id: str | None = Form(default=None),
    user_id: str = Form(default=DEFAULT_USER_ID),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt.")

    filename = Path(file.filename).name
    if not filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname.")

    UPLOAD_DIR.mkdir(exist_ok=True)
    # Pro Chat einen Unterordner, damit gleichnamige Dateien sich nicht überschreiben.
    scope = chat_id or "global"
    chat_dir = UPLOAD_DIR / scope
    chat_dir.mkdir(exist_ok=True)
    dest = chat_dir / filename

    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception:
        raise HTTPException(status_code=500, detail="Datei konnte nicht gespeichert werden.")

    # Record in DB immediately so the UI gets a fast response.
    try:
        db.add(Document(filename=filename, chat_id=chat_id, user_id=user_id))
        await db.commit()
    except Exception:
        pass

    # Embedding + ChromaDB indexing happens in a background thread —
    # the HTTP response is returned to the browser right away.
    background_tasks.add_task(process_document_sync, str(dest), chat_id, user_id)

    return {"status": "ok", "filename": filename}


@router.get("/documents/file")
async def get_document_file(name: str = Query(...)):
    """Liefert eine hochgeladene PDF inline aus, damit sie in der App (Popup) angezeigt
    werden kann. Sucht die Datei in den Upload-Ordnern (global oder chat-spezifisch).
    """
    safe = Path(name).name  # Path-Traversal verhindern: nur den Dateinamen verwenden
    if not safe or not safe.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname.")
    if not UPLOAD_DIR.exists():
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden.")
    matches = [p for p in UPLOAD_DIR.rglob(safe) if p.is_file()]
    if not matches:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden.")
    # Neueste Version nehmen, falls mehrfach hochgeladen
    path = max(matches, key=lambda p: p.stat().st_mtime)
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=safe,
        content_disposition_type="inline",
    )


@router.get("/documents", response_model=list[str])
async def list_documents(
    chat_id: str | None = Query(default=None),
    user_id: str = Query(default=DEFAULT_USER_ID),
    db: AsyncSession = Depends(get_db),
):
    """Listet Dokumente des Nutzers, die tatsächlich in ChromaDB indexiert sind.

    Dokumente werden bewusst nicht nach Chat gruppiert, damit im Quiz auf alle
    Materialien zugegriffen werden kann. (``chat_id`` wird ignoriert, bleibt aus
    Kompatibilitätsgründen erhalten.)
    """
    collection = get_collection()
    if collection is None:
        return []
    try:
        result = collection.get(
            where={"user_id": {"$eq": user_id}},
            include=["metadatas"],
        )
        seen: set[str] = set()
        names: list[str] = []
        for meta in result.get("metadatas") or []:
            source = meta.get("source", "")
            if source and source not in seen:
                seen.add(source)
                names.append(source)
        return sorted(names)
    except Exception:
        return []


@router.delete("/documents")
async def delete_document(
    name: str = Query(...),
    user_id: str = Query(default=DEFAULT_USER_ID),
    db: AsyncSession = Depends(get_db),
):
    """Löscht ein Dokument aus der DB, dem Upload-Ordner und ChromaDB."""
    safe = Path(name).name
    if not safe:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname.")

    # Remove from PostgreSQL
    try:
        await db.execute(delete(Document).where(Document.filename == safe, Document.user_id == user_id))
        await db.commit()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    # Remove from ChromaDB
    collection = get_collection()
    if collection is not None:
        try:
            collection.delete(where={"source": {"$eq": safe}})
        except Exception:
            pass

    # Remove from disk (search all subdirs)
    if UPLOAD_DIR.exists():
        for match in UPLOAD_DIR.rglob(safe):
            try:
                match.unlink()
            except Exception:
                pass

    return {"status": "ok", "deleted": safe}
