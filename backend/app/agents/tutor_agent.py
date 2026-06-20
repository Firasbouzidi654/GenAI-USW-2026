"""TutorAgent — beantwortet Fragen aus Lernmaterial (RAG) und generiert Quizze.

Nutzt LangChain 1.x `create_agent` (LangGraph-basiert). Der Agent entscheidet
selbstständig, welche Dokumente er durchsucht, bevor er antwortet.
Für Quiz-Generierung wird `with_structured_output` eingesetzt.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import extract_text_output, get_llm
from app.models.document import Document
from app.rag.retriever import retrieve_context

logger = logging.getLogger(__name__)

# ── System-Prompts ──────────────────────────────────────────────────────────

_AGENT_SYSTEM_PROMPT = """
Du bist ein intelligenter Tutor-Agent für Studierende an der HTW Berlin.

Deine Aufgaben:
- Fragen zu Lernmaterialien beantworten (nutze immer erst deine Such-Tools)
- Konzepte erklären, Zusammenhänge aufzeigen
- Den Lernfortschritt durch gezielte Rückfragen fördern

Verhalten:
- Suche IMMER zuerst in den Lernmaterialien, bevor du antwortest
- Falls nichts gefunden wird, sage das ehrlich
- Antworte auf Deutsch, es sei denn, der Studierende schreibt Englisch
- Sei ermutigend und klar, nicht übermäßig akademisch
- Wenn du mehrere Dokumente findest, nutze sie alle
""".strip()

_QUIZ_SYSTEM_PROMPT = """
Du bist ein Tutor-Agent der Multiple-Choice- und Wahr/Falsch-Fragen generiert.

Regeln:
- Ausschließlich Fragen, die direkt aus dem bereitgestellten Kontext ableitbar sind
- Alle Fragen und Antworten auf Deutsch
- Multiple-Choice: genau 4 Optionen (A–D), genau eine korrekt
- Wahr/Falsch: keine Optionen, Antwort ist "true" oder "false"
- ca. 70 % Multiple Choice, 30 % Wahr/Falsch
- Variiere den Schwierigkeitsgrad
""".strip()


# ── Pydantic-Schema für Quiz Structured Output ────────────────────────────────

class _QuizQuestionSchema(BaseModel):
    type: str = Field(description="MC oder TF")
    question: str
    options: list[str] | None = None
    correct_answer: str
    explanation: str


class _QuizSchema(BaseModel):
    title: str
    questions: list[_QuizQuestionSchema]


# ── Agent-Factory ─────────────────────────────────────────────────────────────

def create_tutor_agent(db: AsyncSession):
    """Erstellt einen TutorAgent (LangGraph CompiledStateGraph)."""

    @tool
    async def search_learning_material(query: str) -> str:
        """Durchsucht alle hochgeladenen Lernmaterialien nach relevantem Inhalt.
        Nutze dieses Tool für jede inhaltliche Frage des Studierenden."""
        result = await retrieve_context(query, threshold=0.4)
        return result or "Keine relevanten Inhalte für diese Anfrage gefunden."

    @tool
    async def search_in_document(document_name: str, query: str) -> str:
        """Durchsucht ein bestimmtes Dokument nach Inhalt.

        Args:
            document_name: Dateiname des Dokuments (z.B. 'vorlesung1.pdf')
            query: Suchbegriff oder Frage
        """
        result = await retrieve_context(query, source_filter=[document_name], threshold=0.4)
        return result or f"Kein relevanter Inhalt in '{document_name}' gefunden."

    @tool
    async def list_available_documents() -> str:
        """Listet alle hochgeladenen und indizierten Dokumente auf."""
        try:
            result = await db.execute(
                select(Document.filename).order_by(Document.uploaded_at.desc())
            )
            filenames = [row[0] for row in result.all()]
            if not filenames:
                return "Noch keine Dokumente hochgeladen."
            return "Verfügbare Dokumente:\n" + "\n".join(f"- {f}" for f in filenames)
        except Exception as exc:
            logger.warning("Dokument-Abfrage fehlgeschlagen: %s", exc)
            return "Dokumente konnten nicht abgerufen werden."

    llm = get_llm(temperature=0.0)
    return create_agent(
        model=llm,
        tools=[search_learning_material, search_in_document, list_available_documents],
        system_prompt=_AGENT_SYSTEM_PROMPT,
    )


# ── Öffentliche API ───────────────────────────────────────────────────────────

async def run_tutor_agent(message: str, db: AsyncSession) -> str:
    """Führt den TutorAgent für eine Konversationsrunde aus."""
    agent = create_tutor_agent(db)
    try:
        result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
        return extract_text_output(result) or "Ich konnte leider keine Antwort generieren."
    except Exception as exc:
        logger.error("TutorAgent fehlgeschlagen: %s", exc)
        return "Der Tutor ist momentan nicht erreichbar. Bitte später erneut versuchen."


async def generate_quiz_with_agent(
    source_documents: list[str],
    num_questions: int,
    db: AsyncSession,
    course_name: str | None = None,
) -> dict[str, Any]:
    """Generiert ein Quiz via LangChain Structured Output.

    Der TutorAgent holt zuerst den Kontext aus den Dokumenten, dann generiert
    das LLM strukturierte Fragen via `with_structured_output()`.

    Returns:
        Dict mit 'title' und 'questions'.
    Raises:
        ValueError: Wenn kein Kontext gefunden wird.
        RuntimeError: Bei LLM-Fehlern.
    """
    broad_query = "Hauptthemen, wichtige Konzepte, Definitionen, Kernaussagen und Beispiele"
    context = await retrieve_context(
        broad_query,
        source_filter=source_documents,
        n_results=20,
        threshold=None,
    )
    if not context:
        raise ValueError(
            "Für die ausgewählten Dokumente wurde kein indexierter Inhalt gefunden. "
            "Bitte stelle sicher, dass die Dokumente vollständig verarbeitet wurden."
        )

    doc_label = course_name or ", ".join(source_documents)
    user_prompt = (
        f"Erstelle genau {num_questions} Quizfragen basierend auf den folgenden "
        f"Lernunterlagen ({doc_label}).\n\nLernunterlagen-Kontext:\n{context}"
    )

    llm = get_llm(temperature=0.2)
    structured_llm = llm.with_structured_output(_QuizSchema)

    try:
        result: _QuizSchema = await structured_llm.ainvoke([
            SystemMessage(content=_QUIZ_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
    except Exception as exc:
        logger.error("Quiz-Generierung fehlgeschlagen: %s", exc)
        raise RuntimeError("Quiz-Generierung fehlgeschlagen. Bitte später erneut versuchen.")

    if not result.questions:
        raise RuntimeError("Keine Fragen generiert. Bitte erneut versuchen.")

    return {
        "title": result.title or f"Quiz: {doc_label}",
        "questions": [q.model_dump() for q in result.questions],
    }
