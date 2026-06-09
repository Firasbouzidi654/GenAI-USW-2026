"""Tutor Service — generiert Quizze aus hochgeladenen Lernunterlagen via RAG + Gemini."""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.quiz import Quiz
from app.models.quiz_question import QuizQuestion
from app.rag.retriever import retrieve_context

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.gemini_api_key)

# Breite Suchanfrage, um möglichst viele Themen des Dokuments abzudecken
_RAG_QUERY = "Hauptthemen, wichtige Konzepte, Definitionen, Kernaussagen und Beispiele"
_RAG_N_RESULTS = 20

_SYSTEM_PROMPT = """
Du bist ein Tutor-Agent. Deine Aufgabe ist es, Multiple-Choice- und Wahr/Falsch-Fragen
auf Basis von Lernunterlagen zu generieren.

Regeln:
- Generiere ausschließlich Fragen, die direkt aus dem bereitgestellten Kontext ableitbar sind.
- Erfinde keine Fakten, Konzepte oder Aussagen, die nicht im Kontext stehen.
- Alle Fragen, Antwortoptionen und Erklärungen müssen auf Deutsch sein.
- Multiple-Choice-Fragen haben genau 4 Optionen (A, B, C, D). Genau eine ist korrekt.
- Wahr/Falsch-Fragen haben keine Optionen. Die korrekte Antwort ist "true" oder "false".
- Die Erklärung begründet kurz, warum die Antwort korrekt ist.
- Verteile die Fragetypen: ca. 70 % Multiple Choice, ca. 30 % Wahr/Falsch.
- Variiere den Schwierigkeitsgrad: Verständnis-, Anwendungs- und Faktenfragen.
- Gib ausschließlich valides JSON zurück – kein Markdown, keine Erklärungen außerhalb des JSON.

JSON-Schema der Antwort:
{
  "title": "string",
  "questions": [
    {
      "type": "MC",
      "question": "string",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_answer": "A" | "B" | "C" | "D",
      "explanation": "string"
    },
    {
      "type": "TF",
      "question": "string",
      "options": null,
      "correct_answer": "true" | "false",
      "explanation": "string"
    }
  ]
}
""".strip()


def _build_user_prompt(context: str, num_questions: int, source_documents: list[str]) -> str:
    doc_list = ", ".join(source_documents)
    return (
        f"Erstelle genau {num_questions} Quizfragen basierend auf den folgenden Lernunterlagen "
        f"({doc_list}).\n\n"
        f"Lernunterlagen-Kontext:\n{context}"
    )


def _parse_questions(raw: str) -> list[dict]:
    """Parst die Gemini-Antwort und gibt die Fragenliste zurück."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: JSON aus Markdown-Codeblock extrahieren
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if not match:
            raise ValueError("Gemini-Antwort enthält kein valides JSON.")
        data = json.loads(match.group(1))

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("Keine Fragen in der Gemini-Antwort gefunden.")
    return questions, data.get("title", "")


def _validate_question(q: dict, position: int) -> QuizQuestion:
    """Validiert eine einzelne Frage und gibt ein QuizQuestion-Objekt zurück."""
    q_type = q.get("type", "").upper()
    if q_type not in ("MC", "TF"):
        raise ValueError(f"Unbekannter Fragetyp '{q_type}' bei Frage {position}.")

    question_text = str(q.get("question", "")).strip()
    if not question_text:
        raise ValueError(f"Leerer Fragetext bei Frage {position}.")

    correct_answer = str(q.get("correct_answer", "")).strip()
    if q_type == "MC":
        if correct_answer not in ("A", "B", "C", "D"):
            raise ValueError(f"Ungültige MC-Antwort '{correct_answer}' bei Frage {position}.")
        options = q.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError(f"MC-Frage {position} muss genau 4 Optionen haben.")
    else:
        if correct_answer not in ("true", "false"):
            raise ValueError(f"Ungültige TF-Antwort '{correct_answer}' bei Frage {position}.")
        options = None

    return QuizQuestion(
        position=position,
        question_type=q_type,
        question_text=question_text,
        options=options,
        correct_answer=correct_answer,
        explanation=str(q.get("explanation", "")).strip() or None,
    )


async def generate_quiz(
    source_documents: list[str],
    num_questions: int,
    db: AsyncSession,
    course_name: str | None = None,
) -> tuple[Quiz, list[QuizQuestion]]:
    """Generiert ein Quiz aus den angegebenen Dokumenten und speichert es in der DB.

    Returns:
        Tuple aus dem gespeicherten Quiz und der zugehörigen Fragenliste.

    Raises:
        ValueError: Wenn kein Kontext gefunden wurde oder die Gemini-Antwort ungültig ist.
        RuntimeError: Bei Datenbankfehlern.
    """
    if not source_documents:
        raise ValueError("Mindestens ein Dokument muss angegeben werden.")
    if not 1 <= num_questions <= 20:
        raise ValueError("Anzahl der Fragen muss zwischen 1 und 20 liegen.")

    context = await retrieve_context(
        _RAG_QUERY,
        source_filter=source_documents,
        n_results=_RAG_N_RESULTS,
    )
    if not context:
        raise ValueError(
            "Für die ausgewählten Dokumente wurde kein indexierter Inhalt gefunden. "
            "Bitte stelle sicher, dass die Dokumente vollständig verarbeitet wurden."
        )

    user_prompt = _build_user_prompt(context, num_questions, source_documents)

    try:
        response = await _client.aio.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        raw = response.text or ""
    except Exception as exc:
        logger.error("Gemini-Anfrage fehlgeschlagen: %s", exc)
        raise RuntimeError("Quiz-Generierung fehlgeschlagen. Bitte später erneut versuchen.")

    try:
        questions_data, generated_title = _parse_questions(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Gemini-Antwort konnte nicht geparst werden: %s\nRaw: %s", exc, raw[:500])
        raise RuntimeError("Gemini hat kein auswertbares Quiz zurückgegeben. Bitte erneut versuchen.")

    doc_label = course_name or ", ".join(source_documents)
    title = generated_title or f"Quiz: {doc_label}"

    quiz = Quiz(
        title=title,
        source_documents=source_documents,
        course_name=course_name,
        question_count=len(questions_data),
    )

    validated_questions: list[QuizQuestion] = []
    for i, q_data in enumerate(questions_data, start=1):
        try:
            validated_questions.append(_validate_question(q_data, i))
        except ValueError as exc:
            logger.warning("Frage %d übersprungen: %s", i, exc)

    if not validated_questions:
        raise RuntimeError("Keine validen Fragen generiert. Bitte erneut versuchen.")

    quiz.question_count = len(validated_questions)

    try:
        db.add(quiz)
        await db.flush()  # quiz.id verfügbar machen ohne commit
        for q in validated_questions:
            q.quiz_id = quiz.id
            db.add(q)
        await db.commit()
        await db.refresh(quiz)
    except Exception as exc:
        logger.error("Datenbank-Fehler beim Speichern des Quizzes: %s", exc)
        raise RuntimeError("Quiz konnte nicht gespeichert werden.")

    return quiz, validated_questions