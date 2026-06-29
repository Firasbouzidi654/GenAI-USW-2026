from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.planner_agent import run_planner_agent
from app.agents.orchestrator import should_route_to_moodle_context
from app.core.database import get_db
from app.services.moodle_context_service import get_moodle_context_for_message

router = APIRouter()


class StudyAdvisorRequest(BaseModel):
    message: str


class StudyAdvisorResponse(BaseModel):
    answer: str


@router.post("/ai/study-advisor", response_model=StudyAdvisorResponse)
async def study_advisor(body: StudyAdvisorRequest, db: AsyncSession = Depends(get_db)):
    if should_route_to_moodle_context(body.message):
        answer = await get_moodle_context_for_message(body.message)
        return {"answer": answer}
    answer = await run_planner_agent(body.message, db)
    return {"answer": answer}
