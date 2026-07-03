"""Evaluator-Endpunkte — Wissenslücken-Analyse via EvaluatorAgent."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.evaluator_agent import get_knowledge_gap_analysis, run_evaluator_agent
from app.core.database import get_db

router = APIRouter()


class EvaluatorRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nachricht darf nicht leer sein.")
        return value


class EvaluatorResponse(BaseModel):
    analysis: str


@router.post("/ai/evaluate", response_model=EvaluatorResponse)
async def evaluate_knowledge(body: EvaluatorRequest, db: AsyncSession = Depends(get_db)):
    """EvaluatorAgent beantwortet Fragen zum Lernfortschritt und identifiziert Wissenslücken."""
    try:
        analysis = await run_evaluator_agent(body.message, db)
        return {"analysis": analysis}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"EvaluatorAgent nicht verfügbar: {exc}")


@router.get("/ai/knowledge-gaps", response_model=EvaluatorResponse)
async def get_knowledge_gaps(db: AsyncSession = Depends(get_db)):
    """Vollständige automatische Wissenslücken-Analyse aller Quiz-Ergebnisse."""
    try:
        analysis = await get_knowledge_gap_analysis(db)
        return {"analysis": analysis}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"EvaluatorAgent nicht verfügbar: {exc}")
