from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.study_advisor_service import get_study_advice

router = APIRouter()


class StudyAdvisorRequest(BaseModel):
    message: str


class StudyAdvisorResponse(BaseModel):
    answer: str


@router.post("/ai/study-advisor", response_model=StudyAdvisorResponse)
async def study_advisor(body: StudyAdvisorRequest, db: AsyncSession = Depends(get_db)):
    answer = await get_study_advice(body.message, db)
    return {"answer": answer}
