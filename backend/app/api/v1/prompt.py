import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from google import genai
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.chat import ChatMessage
from app.rag.retriever import retrieve_context

client = genai.Client(api_key=settings.gemini_api_key)

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str


class PromptResponse(BaseModel):
    response: str


def _build_prompt(user_prompt: str, context: str) -> str:
    if context:
        return f"Kontext aus den Unterlagen:\n{context}\n\nFrage: {user_prompt}"
    return user_prompt


@router.post("/prompt", response_model=PromptResponse)
async def handle_prompt(body: PromptRequest, db: AsyncSession = Depends(get_db)):
    context = await retrieve_context(body.prompt)
    full_prompt = _build_prompt(body.prompt, context)

    try:
        result = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=full_prompt)
    except Exception:
        raise HTTPException(status_code=502, detail="KI-Dienst nicht erreichbar.")

    try:
        db.add(ChatMessage(prompt=body.prompt, response=result.text))
        await db.commit()
    except Exception:
        pass

    return PromptResponse(response=result.text)


@router.post("/prompt/stream")
async def stream_prompt(body: PromptRequest):
    context = await retrieve_context(body.prompt)
    full_prompt = _build_prompt(body.prompt, context)

    async def generate():
        try:
            stream = await client.aio.models.generate_content_stream(
                model="gemini-3.1-flash-lite-preview", contents=full_prompt
            )
            async for chunk in stream:
                if chunk.text:
                    yield f"data: {json.dumps(chunk.text)}\n\n"
        except Exception:
            yield "data: [ERROR]\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")