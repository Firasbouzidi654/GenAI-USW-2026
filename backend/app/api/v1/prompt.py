from fastapi import APIRouter
from google import genai
from pydantic import BaseModel

from app.core.config import settings
from app.rag.retriever import retrieve_context

client = genai.Client(api_key=settings.gemini_api_key)

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str


class PromptResponse(BaseModel):
    response: str


@router.post("/prompt", response_model=PromptResponse)
async def handle_prompt(body: PromptRequest):
    context = await retrieve_context(body.prompt)

    if context:
        full_prompt = f"Kontext aus den Unterlagen:\n{context}\n\nFrage: {body.prompt}"
    else:
        full_prompt = body.prompt

    result = client.models.generate_content(model="gemini-1.5-flash", contents=full_prompt)
    return PromptResponse(response=result.text)