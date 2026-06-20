"""Email-Summary-Service — fasst bereits vorgefilterte HTW-Berlin-E-Mails via
Gemini auf Französisch zusammen, strukturiert in urgent_actions / important_updates / events.

Erwartet nur E-Mails, die app.services.email_filter_service.filter_important_emails()
bereits als relevant eingestuft hat - das reduziert den Gemini-Tokenverbrauch erheblich.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.base import run_with_model_fallback
from app.services.email_models import FetchedEmail

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
Tu es un assistant qui aide un·e étudiant·e de la HTW Berlin à traiter ses emails
universitaires. Les emails fournis ont déjà été pré-filtrés : ils sont tous
potentiellement liés aux études (pas besoin de les filtrer à nouveau).

Structure le résultat en trois catégories :

1. urgent_actions : actions nécessitant une réponse ou une action avant une échéance
   précise (devoirs à rendre, examens à venir, délais d'inscription, formulaires à
   soumettre...). Pour chacune, donne : title, deadline (reprends la date si connue,
   sinon une chaîne vide), priority ("HIGH", "MEDIUM" ou "LOW" selon l'urgence réelle),
   et reason (courte explication).

2. important_updates : informations importantes ne nécessitant pas d'action immédiate
   (feedback reçu, changement de salle/horaire, annonces de cours, résultats...).
   Pour chacune : title, summary (court résumé en français simple).

3. events : événements avec une date concrète (séances de révision, rendez-vous,
   sessions d'information, ateliers...). Pour chacun : title, date, location
   (chaîne vide si inconnu).

Rédige aussi un résumé global ("summary") en français simple qui met en avant les
échéances les plus proches et les actions prioritaires.

N'invente rien : si une information n'est pas présente dans l'email, laisse le champ
vide plutôt que de deviner.
""".strip()


class _UrgentActionSchema(BaseModel):
    title: str
    deadline: str = ""
    priority: str = "MEDIUM"
    reason: str = ""


class _ImportantUpdateSchema(BaseModel):
    title: str
    summary: str = ""


class _EventSchema(BaseModel):
    title: str
    date: str = ""
    location: str = ""


class _EmailDigestSchema(BaseModel):
    summary: str
    urgent_actions: list[_UrgentActionSchema] = Field(default_factory=list)
    important_updates: list[_ImportantUpdateSchema] = Field(default_factory=list)
    events: list[_EventSchema] = Field(default_factory=list)


def _format_emails_for_prompt(emails: list[FetchedEmail]) -> str:
    blocks = []
    for i, e in enumerate(emails, start=1):
        blocks.append(
            f"--- Email {i} ---\n"
            f"Von: {e.sender}\n"
            f"Betreff: {e.subject}\n"
            f"Datum: {e.date}\n"
            f"Inhalt: {e.body[:1500]}"
        )
    return "\n\n".join(blocks)


def _empty_digest(summary: str) -> dict:
    return {"summary": summary, "urgent_actions": [], "important_updates": [], "events": []}


async def summarize_emails(emails: list[FetchedEmail]) -> dict:
    """Fasst die übergebenen (bereits gefilterten) E-Mails via Gemini zusammen
    (mit Modell-Fallback, siehe app.agents.base.run_with_model_fallback).

    Raises:
        RuntimeError: wenn alle konfigurierten Gemini-Modelle fehlschlagen.
    """
    if not emails:
        return _empty_digest("Keine wichtigen E-Mails gefunden.")

    user_prompt = "Voici les emails à analyser :\n\n" + _format_emails_for_prompt(emails)

    async def _invoke(llm):
        structured_llm = llm.with_structured_output(_EmailDigestSchema)
        return await structured_llm.ainvoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])

    try:
        result: _EmailDigestSchema = await run_with_model_fallback(_invoke, temperature=0.2)
    except Exception as exc:
        logger.error("Email-Zusammenfassung fehlgeschlagen: %s", exc)
        raise RuntimeError("KI-E-Mail-Zusammenfassung fehlgeschlagen.") from exc

    return result.model_dump()
