import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import calendar, career, curriculum, evaluator, exams, grades, history, lsf_mock, moodle, planner, profile, prompt, study_advisor, tutor, upload
from app.core.database import AsyncSessionLocal, Base, engine
import app.models
from app.services.lsf_sync import sync_lsf_to_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Leichte Migration: chat_id/user_id-Spalten für bestehende documents-Tabellen
            # ergänzen (create_all fügt keine Spalten zu vorhandenen Tabellen hinzu).
            if conn.dialect.name == "postgresql":
                await conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS chat_id VARCHAR(64)"))
                await conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) DEFAULT 'local'"))
                await conn.execute(text("ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS source VARCHAR(16) DEFAULT 'lsf'"))
                await conn.execute(text("ALTER TABLE curriculum_modules ADD COLUMN IF NOT EXISTS module_type VARCHAR(32)"))
    except Exception:
        pass

    # Auto-Seed: LSF-Daten beim Start idempotent in die DB laden
    try:
        async with AsyncSessionLocal() as db:
            await sync_lsf_to_db(db)
    except Exception as exc:
        logger.warning("LSF-Auto-Seed beim Start fehlgeschlagen: %s", exc)

    yield


app = FastAPI(title="Adaptive Study & Career Agent API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lsf_mock.router, prefix="/api")
app.include_router(moodle.router, prefix="/api")
app.include_router(curriculum.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(prompt.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(exams.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(grades.router, prefix="/api")
app.include_router(planner.router, prefix="/api")
app.include_router(study_advisor.router, prefix="/api")
app.include_router(evaluator.router, prefix="/api")
app.include_router(career.router, prefix="/api")
app.include_router(tutor.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
