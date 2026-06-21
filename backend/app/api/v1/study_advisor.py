from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.planner_agent import run_planner_agent
from app.core.database import get_db

router = APIRouter()


class StudyAdvisorRequest(BaseModel):
    message: str


class StudyAdvisorResponse(BaseModel):
    answer: str


@router.post("/ai/study-advisor", response_model=StudyAdvisorResponse)
async def study_advisor(body: StudyAdvisorRequest, db: AsyncSession = Depends(get_db)):
    answer = await run_planner_agent(body.message, db)
    return {"answer": answer}
