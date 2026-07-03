"""Prompt-Endpunkt — universeller Chat-Einstieg ins Multi-Agent-System.

Die Anfrage geht an den Orchestrator (Supervisor), der entscheidet, welcher
Spezial-Agent (Tutor, Evaluator, Planner, Career) zuständig ist, und sie bei
Bedarf verkettet.
"""

import json
import re
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import ainvoke_with_model_fallback
from app.agents.orchestrator import run_orchestrator
from app.core.database import get_db
from app.models.chat import ChatMessage

router = APIRouter()

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)
    chat_id: str | None = Field(default=None, max_length=64)
    user_id: str = Field(default="local", min_length=1, max_length=64)
    moodle_context: dict[str, Any] | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt darf nicht leer sein.")
        return value

    @field_validator("chat_id", "user_id")
    @classmethod
    def ids_must_be_safe(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return value
        if not _SAFE_ID_RE.fullmatch(value):
            raise ValueError("ID enthält ungültige Zeichen.")
        return value


class TitleRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Frage darf nicht leer sein.")
        return value


class TitleResponse(BaseModel):
    title: str


_TITLE_SYSTEM = (
    "Du formulierst aus der ersten Nutzerfrage eines Chats einen sehr kurzen, "
    "THEMATISCHEN Titel (höchstens 5 Wörter). Beschreibe das Thema/Anliegen, "
    "wiederhole nicht die ganze Frage und nutze keine Anführungszeichen oder "
    "Satzzeichen am Ende. Antworte AUSSCHLIESSLICH mit dem Titel."
)


@router.post("/chat/title", response_model=TitleResponse)
async def chat_title(body: TitleRequest):
    """Analysiert die erste Frage eines Chats und gibt einen kurzen Themen-Titel zurück."""
    q = (body.question or "").strip()
    if not q:
        return TitleResponse(title="Neuer Chat")
    fallback = q[:40]
    try:
        resp = await ainvoke_with_model_fallback([
            SystemMessage(content=_TITLE_SYSTEM),
            HumanMessage(content=q[:2000]),
        ], temperature=0.0)
        content = (
            resp.content if isinstance(resp.content, str)
            else " ".join(p.get("text", "") for p in resp.content if isinstance(p, dict))
        )
        title = content.strip().split("\n")[0].strip().strip("\"'")
        # Mögliches „Titel:"-Präfix entfernen
        if ":" in title[:8].lower() and title.lower().startswith("titel"):
            title = title.split(":", 1)[1].strip()
        title = title[:60].strip(" .\"'")
        return TitleResponse(title=title or fallback)
    except Exception:
        return TitleResponse(title=fallback)


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
