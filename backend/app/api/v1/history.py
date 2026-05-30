from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.chat import ChatMessage

router = APIRouter()


class ChatHistoryItem(BaseModel):
    id: int
    prompt: str
    response: str
    created_at: datetime


@router.get("/history", response_model=list[ChatHistoryItem])
async def get_history(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(ChatMessage).order_by(ChatMessage.created_at.desc()).limit(50)
        )
        return result.scalars().all()
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")
