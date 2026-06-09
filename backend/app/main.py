from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import calendar, exams, grades, history, job_agent, planner, prompt, study_advisor, tutor, upload
from app.core.database import Base, engine
import app.models


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
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

app.include_router(prompt.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(exams.router, prefix="/api")
app.include_router(job_agent.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(grades.router, prefix="/api")
app.include_router(planner.router, prefix="/api")
app.include_router(study_advisor.router, prefix="/api")
app.include_router(tutor.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
