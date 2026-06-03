import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class JobSearchParams(BaseModel):
    keyword: str = ""
    location: str = ""
    experienceLevel: str = ""
    remote: str = ""
    jobType: str = ""
    easyApply: bool = False


@router.post("/job-agent/run")
async def run_job_agent(params: JobSearchParams):
    # Webhook URL is read from N8N_JOB_AGENT_WEBHOOK_URL in backend/.env
    webhook_url = settings.n8n_job_agent_webhook_url
    if not webhook_url:
        raise HTTPException(
            status_code=503,
            detail=(
                "N8N_JOB_AGENT_WEBHOOK_URL is not configured. "
                "Set it in backend/.env and restart the backend."
            ),
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(webhook_url, json=params.model_dump())
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"n8n returned an error: HTTP {e.response.status_code}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach n8n webhook: {e}",
        )

    return {"status": "triggered", "message": "Job Search Agent successfully launched."}
