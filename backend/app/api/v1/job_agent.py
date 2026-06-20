import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.career import get_career_analysis
from app.core.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

_FALLBACK_CAREER_PROFILE = {
    "best_match": "Data Engineer",
    "skills": ["Python", "SQL", "Databases"],
    "missing_skills": ["Docker", "AWS"],
    "target_location": "Germany",
}


def _as_plain_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    try:
        return dict(value)
    except (TypeError, ValueError):
        logger.warning(
            "Could not convert career profile (%r) to dict - using fallback.",
            type(value),
        )
        return _FALLBACK_CAREER_PROFILE


def _role_from_best_match_object(best_match: dict) -> dict:
    return {
        "title": best_match.get("title", ""),
        "match": best_match.get("match", best_match.get("match_percent")),
        "market_demand": best_match.get("market_demand", ""),
        "salary": best_match.get("salary", best_match.get("salary_range_eur", "")),
        "missing_skills": best_match.get("missing_skills", []),
        "recommended_certifications": best_match.get(
            "recommended_certifications", []
        ),
        "recommended_projects": best_match.get("recommended_projects", []),
    }


def _role_from_roles_list(top_role: dict) -> dict:
    return {
        "title": top_role.get("title", ""),
        "match": top_role.get("match_percent"),
        "market_demand": top_role.get("market_demand", ""),
        "salary": top_role.get("salary_range_eur", ""),
        "missing_skills": top_role.get("missing_skills", []),
        "recommended_certifications": top_role.get(
            "recommended_certifications", []
        ),
        "recommended_projects": top_role.get("recommended_projects", []),
    }


def _normalize_to_best_match(profile: dict) -> dict:
    """
    Keep only the single best career match.
    """

    best_match = profile.get("best_match")
    target_location = profile.get("target_location", "Germany")

    if isinstance(best_match, dict):
        role = _role_from_best_match_object(best_match)
        title = role["title"]

    elif isinstance(best_match, str) and best_match:
        role = {"title": best_match}
        title = best_match

    else:
        roles = profile.get("roles") or []

        if roles:
            role = _role_from_roles_list(roles[0])
            title = role["title"]
        else:
            role = None
            title = None

    if not title:
        return _FALLBACK_CAREER_PROFILE

    return {
        "best_match": title,
        "target_location": target_location,
        "roles": [role],
    }


@router.post("/job-agent/run")
async def run_job_agent(
    cv: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    webhook_url = settings.n8n_job_agent_webhook_url

    if not webhook_url:
        raise HTTPException(
            status_code=503,
            detail="N8N_JOB_AGENT_WEBHOOK_URL is not configured. Set it in backend/.env and restart the backend.",
        )

    if cv.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Nur PDF-Dateien erlaubt.",
        )

    try:
        career_profile = _as_plain_dict(await get_career_analysis(db))
    except HTTPException as exc:
        logger.warning(
            "Career analysis unavailable (%s) - using fallback profile.",
            exc.detail,
        )
        career_profile = _FALLBACK_CAREER_PROFILE

    career_profile = _normalize_to_best_match(career_profile)

    cv_bytes = await cv.read()

    print(
        "CAREER PROFILE SENT TO N8N =",
        json.dumps(career_profile, ensure_ascii=False),
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                webhook_url,
                files={
                    "cv": (
                        cv.filename,
                        cv_bytes,
                        "application/pdf",
                    ),
                },
                data={
                    "career_profile": json.dumps(career_profile),
                },
            )

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

    # Return JSON if n8n responds with JSON.
    # Otherwise return the raw response for debugging.
    try:
        return response.json()

    except Exception:
        return {
            "success": response.status_code < 400,
            "status_code": response.status_code,
            "message": "n8n workflow triggered, but n8n did not return JSON",
            "raw_response": response.text,
        }