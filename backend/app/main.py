from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import calendar, career, curriculum, email_agent, evaluator, exams, grades, history, job_agent, lsf_mock, moodle, planner, profile, prompt, study_advisor, tutor, upload
from app.core.database import Base, engine
import app.models


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            if conn.dialect.name == "postgresql":
                await conn.execute(text("ALTER TABLE focus_sessions ALTER COLUMN focus_minutes TYPE DOUBLE PRECISION USING focus_minutes::double precision"))
                await conn.execute(text("ALTER TABLE focus_sessions ALTER COLUMN break_minutes TYPE DOUBLE PRECISION USING break_minutes::double precision"))
                await conn.execute(text("ALTER TABLE focus_sessions ALTER COLUMN total_focus_time TYPE DOUBLE PRECISION USING total_focus_time::double precision"))
                await conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS chat_id VARCHAR(64)"))
                await conn.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) DEFAULT 'local'"))
                await conn.execute(text("ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS source VARCHAR(16) DEFAULT 'lsf'"))
                await conn.execute(text("ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS category VARCHAR(64)"))
                await conn.execute(text("ALTER TABLE curriculum_modules ADD COLUMN IF NOT EXISTS module_type VARCHAR(32)"))
    except Exception:
        pass
    yield


app = FastAPI(title="KI-Lern- & Jobagent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lsf_mock.router, prefix="/api")
app.include_router(moodle.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(curriculum.router, prefix="/api")
app.include_router(prompt.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(exams.router, prefix="/api")
app.include_router(job_agent.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(grades.router, prefix="/api")
app.include_router(planner.router, prefix="/api")
app.include_router(study_advisor.router, prefix="/api")
app.include_router(evaluator.router, prefix="/api")
app.include_router(career.router, prefix="/api")
app.include_router(email_agent.router, prefix="/api")
app.include_router(tutor.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
