"""Email-Agent-Endpunkt — liest HTW-Berlin-Mails per IMAP und fasst sie via Gemini zusammen."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.services.email_filter_service import filter_important_emails
from app.services.email_models import FetchedEmail
from app.services.email_summary_service import summarize_emails
from app.services.imap_email_service import fetch_latest_emails

logger = logging.getLogger(__name__)

router = APIRouter()

_EMAIL_LIMIT = 20


def _raw_email_payload(emails: list[FetchedEmail]) -> list[dict]:
    return [
        {"subject": e.subject, "sender": e.sender, "date": e.date, "snippet": e.snippet}
        for e in emails
    ]


@router.get("/email-agent/summary")
async def get_email_summary():
    try:
        emails = await asyncio.to_thread(fetch_latest_emails, _EMAIL_LIMIT)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # Keyword pre-filter runs before Gemini ever sees anything - cuts noise
    # (parties, newsletters, mailing-list digests) and Gemini token usage.
    important_emails = filter_important_emails(emails)
    logger.info(
        "Email-Filter: %d von %d E-Mails als relevant eingestuft.",
        len(important_emails), len(emails),
    )

    try:
        digest = await summarize_emails(important_emails)
        return {
            "success": True,
            "email_count": len(emails),
            "filtered_count": len(important_emails),
            "summary": digest["summary"],
            "urgent_actions": digest["urgent_actions"],
            "important_updates": digest["important_updates"],
            "events": digest["events"],
            "raw_emails": _raw_email_payload(important_emails),
        }
    except RuntimeError as exc:
        # Gemini unavailable - still show the Python-filtered important emails
        # (not the full unfiltered inbox) so the request isn't wasted.
        logger.warning("Email-Zusammenfassung nicht verfügbar (%s) - zeige gefilterte Rohdaten.", exc)
        return {
            "success": True,
            "email_count": len(emails),
            "filtered_count": len(important_emails),
            "summary": "AI Summary unavailable",
            "urgent_actions": [],
            "important_updates": [],
            "events": [],
            "raw_emails": _raw_email_payload(important_emails),
        }
