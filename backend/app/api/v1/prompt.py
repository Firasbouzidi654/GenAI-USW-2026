import json

from fastapi import APIRouter, Depends
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


def _build_prompt(user_prompt: str, context: str) -> str:
    if context:
        return f"Kontext aus den Unterlagen:\n{context}\n\nFrage: {user_prompt}"
    return user_prompt


@router.post("/prompt")
async def prompt(body: PromptRequest, db: AsyncSession = Depends(get_db)):
    context = await retrieve_context(body.prompt)
    full_prompt = _build_prompt(body.prompt, context)

    async def generate():
        accumulated = []
        try:
            stream = await client.aio.models.generate_content_stream(
                model="gemini-3.1-flash-lite-preview", contents=full_prompt
            )
            async for chunk in stream:
                if chunk.text:
                    accumulated.append(chunk.text)
                    yield f"data: {json.dumps(chunk.text)}\n\n"
        except Exception:
            yield "data: [ERROR]\n\n"
        finally:
            full_response = "".join(accumulated)
            if full_response:
                try:
                    db.add(ChatMessage(prompt=body.prompt, response=full_response))
                    await db.commit()
                except Exception:
                    pass
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")