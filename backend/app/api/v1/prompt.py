"""Prompt-Endpunkt — universeller Chat-Einstieg ins Multi-Agent-System.

Die Anfrage geht an den Orchestrator (Supervisor), der entscheidet, welcher
Spezial-Agent (Tutor, Evaluator, Planner, Career) zuständig ist, und sie bei
Bedarf verkettet.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import run_orchestrator
from app.core.database import get_db
from app.models.chat import ChatMessage

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str
    chat_id: str | None = None
    user_id: str = "local"
    moodle_context: dict[str, Any] | None = None


@router.post("/prompt")
async def prompt(body: PromptRequest, db: AsyncSession = Depends(get_db)):
    """Orchestrator beantwortet die Frage und koordiniert dafür die Spezial-Agents."""

    async def generate():
        try:
            answer = await run_orchestrator(
                body.prompt,
                db,
                body.chat_id,
                body.user_id,
                moodle_context=body.moodle_context,
            )
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
