from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import calendar, career, email_agent, evaluator, exams, focus_time, grades, history, job_agent, language_tutor, moodle_mock, planner, prompt, study_advisor, tutor, upload
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

app.include_router(moodle_mock.router, prefix="/api")
app.include_router(prompt.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(exams.router, prefix="/api")
app.include_router(focus_time.router, prefix="/api")
app.include_router(job_agent.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(grades.router, prefix="/api")
app.include_router(planner.router, prefix="/api")
app.include_router(study_advisor.router, prefix="/api")
app.include_router(evaluator.router, prefix="/api")
app.include_router(language_tutor.router, prefix="/api")
app.include_router(career.router, prefix="/api")
app.include_router(email_agent.router, prefix="/api")
app.include_router(tutor.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
