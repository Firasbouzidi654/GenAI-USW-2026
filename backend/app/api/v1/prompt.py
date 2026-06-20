"""Prompt-Endpunkt — leitet Fragen des Studierenden an den TutorAgent weiter.

Der TutorAgent entscheidet selbstständig, ob und welche Dokumente er durchsucht,
bevor er antwortet (echter ReAct-Loop statt einfacher RAG-Pipeline).
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tutor_agent import run_tutor_agent
from app.core.database import get_db
from app.models.chat import ChatMessage

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str


@router.post("/prompt")
async def prompt(body: PromptRequest, db: AsyncSession = Depends(get_db)):
    """TutorAgent beantwortet die Frage — mit autonomer Dokumentensuche (RAG + Tool Calling)."""

    async def generate():
        try:
            answer = await run_tutor_agent(body.prompt, db)
        except Exception:
            yield f"data: {json.dumps('[ERROR]')}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Antwort in sinnvolle Chunks aufteilen (wortweise), damit das SSE-Streaming
        # beim Client weiterhin animiert wirkt (TutorAgent gibt erst am Ende zurück)
        words = answer.split(" ")
        chunk_size = 8
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            yield f"data: {json.dumps(chunk)}\n\n"

        try:
            db.add(ChatMessage(prompt=body.prompt, response=answer))
            await db.commit()
        except Exception:
            pass

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
