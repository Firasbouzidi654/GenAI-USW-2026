"""Tutor Service — Brücke zwischen FastAPI-Endpunkten und dem TutorAgent.

Validiert Eingaben, delegiert an den TutorAgent und speichert das Ergebnis in der DB.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tutor_agent import generate_quiz_with_agent
from app.models.quiz import Quiz
from app.models.quiz_question import QuizQuestion

logger = logging.getLogger(__name__)

_VALID_TYPES = {"MC", "TF"}
_VALID_MC_ANSWERS = {"A", "B", "C", "D"}
_VALID_TF_ANSWERS = {"true", "false"}


def _validate_and_build_question(q: dict, position: int) -> QuizQuestion:
    q_type = str(q.get("type", "")).upper()
    if q_type not in _VALID_TYPES:
        raise ValueError(f"Unbekannter Fragetyp '{q_type}' bei Frage {position}.")

    question_text = str(q.get("question", "")).strip()
    if not question_text:
        raise ValueError(f"Leerer Fragetext bei Frage {position}.")

    correct_answer = str(q.get("correct_answer", "")).strip()

    if q_type == "MC":
        if correct_answer not in _VALID_MC_ANSWERS:
            raise ValueError(f"Ungültige MC-Antwort '{correct_answer}' bei Frage {position}.")
        options = q.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError(f"MC-Frage {position} muss genau 4 Optionen haben.")
    else:
        if correct_answer not in _VALID_TF_ANSWERS:
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
    chat_id: str | None = None,
    user_id: str = "local",
) -> tuple[Quiz, list[QuizQuestion]]:
    """Generiert ein Quiz via TutorAgent und speichert es in der DB.

    Returns:
        Tuple aus gespeichertem Quiz und Fragenliste.
    Raises:
        ValueError: Ungültige Eingabe oder kein Inhalt gefunden.
        RuntimeError: Agent- oder DB-Fehler.
    """
    if not source_documents:
        raise ValueError("Mindestens ein Dokument muss angegeben werden.")
    if not 1 <= num_questions <= 20:
        raise ValueError("Anzahl der Fragen muss zwischen 1 und 20 liegen.")

    # Delegation an den TutorAgent
    quiz_data = await generate_quiz_with_agent(
        source_documents=source_documents,
        num_questions=num_questions,
        db=db,
        course_name=course_name,
        chat_id=chat_id,
        user_id=user_id,
    )

    doc_label = course_name or ", ".join(source_documents)
    title = quiz_data.get("title") or f"Quiz: {doc_label}"

    quiz = Quiz(
        title=title,
        source_documents=source_documents,
        course_name=course_name,
        question_count=0,
    )

    validated_questions: list[QuizQuestion] = []
    for i, q_data in enumerate(quiz_data.get("questions", []), start=1):
        try:
            validated_questions.append(_validate_and_build_question(q_data, i))
        except ValueError as exc:
            logger.warning("Frage %d übersprungen: %s", i, exc)

    if not validated_questions:
        raise RuntimeError("Keine validen Fragen generiert. Bitte erneut versuchen.")

    quiz.question_count = len(validated_questions)

    try:
        db.add(quiz)
        await db.flush()
        for q in validated_questions:
            q.quiz_id = quiz.id
            db.add(q)
        await db.commit()
        await db.refresh(quiz)
    except Exception as exc:
        logger.error("DB-Fehler beim Speichern des Quizzes: %s", exc)
        raise RuntimeError("Quiz konnte nicht gespeichert werden.")

    return quiz, validated_questions
