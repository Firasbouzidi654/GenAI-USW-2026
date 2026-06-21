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
- Suche IMMER zuerst in den hochgeladenen Lernmaterialien (search_learning_material)
- Wenn dort nichts Relevantes gefunden wird, prüfe die in Moodle belegten Kurse:
  rufe list_moodle_courses auf, wähle den thematisch passenden Kurs und lade dessen
  Materialien mit index_moodle_course nach. Suche danach erneut mit search_learning_material.
- Falls auch dann nichts gefunden wird, sage das ehrlich
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


def _is_valid_quiz_question(q: dict) -> bool:
    """Strukturelle Gültigkeitsprüfung (MC: 4 Optionen + A–D; TF: true/false)."""
    qtype = str(q.get("type", "")).upper()
    if qtype not in ("MC", "TF"):
        return False
    if not str(q.get("question", "")).strip():
        return False
    ans = str(q.get("correct_answer", "")).strip()
    if qtype == "MC":
        opts = q.get("options")
        return ans in ("A", "B", "C", "D") and isinstance(opts, list) and len(opts) == 4
    return ans in ("true", "false")


# ── Agent-Factory ─────────────────────────────────────────────────────────────

def create_tutor_agent(db: AsyncSession, chat_id: str | None = None, user_id: str = "local"):
    """Erstellt einen TutorAgent (LangGraph CompiledStateGraph).

    Dokumente werden chat-ÜBERGREIFEND durchsucht (nur nach ``user_id`` gefiltert),
    damit alle hochgeladenen Materialien zur Verfügung stehen.
    """

    @tool
    async def search_learning_material(query: str) -> str:
        """Durchsucht ALLE hochgeladenen Lernmaterialien nach Inhalt.
        Nutze dieses Tool für jede inhaltliche Frage des Studierenden, auch für
        allgemeine Fragen wie 'Worum geht es in dem Dokument?'."""
        # threshold=None + chat_id=None: über alle Dokumente des Nutzers suchen.
        result = await retrieve_context(
            query, n_results=10, threshold=None, chat_id=None, user_id=user_id
        )
        return result or "Es wurden noch keine Dokumente hochgeladen."

    @tool
    async def search_in_document(document_name: str, query: str) -> str:
        """Durchsucht ein bestimmtes Dokument nach Inhalt.

        Args:
            document_name: Dateiname des Dokuments (z.B. 'vorlesung1.pdf')
            query: Suchbegriff oder Frage
        """
        result = await retrieve_context(
            query, source_filter=[document_name], threshold=None,
            n_results=10, chat_id=None, user_id=user_id,
        )
        return result or f"Kein relevanter Inhalt in '{document_name}' gefunden."

    @tool
    async def list_available_documents() -> str:
        """Listet alle hochgeladenen Dokumente auf."""
        try:
            stmt = (
                select(Document.filename)
                .where(Document.user_id == user_id)
                .order_by(Document.uploaded_at.desc())
            )
            result = await db.execute(stmt)
            filenames = list(dict.fromkeys(row[0] for row in result.all()))
            if not filenames:
                return "Es wurden noch keine Dokumente hochgeladen."
            return "Verfügbare Dokumente:\n" + "\n".join(f"- {f}" for f in filenames)
        except Exception as exc:
            logger.warning("Dokument-Abfrage fehlgeschlagen: %s", exc)
            return "Dokumente konnten nicht abgerufen werden."

    @tool
    async def list_moodle_courses() -> str:
        """Listet die in Moodle belegten Kurse (nach Semester) auf. Nutze dies, wenn
        in den hochgeladenen Dokumenten nichts Passendes zu einer Themenfrage steht."""
        from app.services import moodle_service
        if not moodle_service.is_configured():
            return "Moodle ist nicht verbunden (kein Token hinterlegt)."
        try:
            courses = await moodle_service.get_courses()
        except moodle_service.MoodleError as exc:
            return f"Moodle-Kurse konnten nicht geladen werden: {exc}"
        if not courses:
            return "Keine belegten Moodle-Kurse gefunden."
        return "Belegte Moodle-Kurse:\n" + "\n".join(
            f"- {c['fullname']} ({c['semester']})" for c in courses
        )

    @tool
    async def index_moodle_course(course_name: str) -> str:
        """Lädt die Materialien (PDFs) eines belegten Moodle-Kurses herunter und
        indiziert sie für die Suche. Danach search_learning_material erneut aufrufen.

        Args:
            course_name: Name (oder Teil) des belegten Kurses, z.B. 'Statistik'.
        """
        from app.services import moodle_service
        if not moodle_service.is_configured():
            return "Moodle ist nicht verbunden (kein Token hinterlegt)."
        try:
            res = await moodle_service.index_course_by_name(course_name, chat_id, user_id)
        except moodle_service.MoodleError as exc:
            return f"Moodle-Materialien konnten nicht geladen werden: {exc}"
        if not res.get("matched"):
            avail = ", ".join(res.get("available", [])[:10])
            return f"{res.get('message','Kein Kurs gefunden.')} Verfügbar: {avail}"
        return (
            f"{res['files_indexed']} von {res['files_found']} Dateien aus '{res['course']}' "
            f"({res['semester']}) indiziert. Du kannst jetzt erneut suchen."
        )

    llm = get_llm(temperature=0.0)
    return create_agent(
        model=llm,
        tools=[
            search_learning_material,
            search_in_document,
            list_available_documents,
            list_moodle_courses,
            index_moodle_course,
        ],
        system_prompt=_AGENT_SYSTEM_PROMPT,
    )


# ── Öffentliche API ───────────────────────────────────────────────────────────

async def run_tutor_agent(
    message: str, db: AsyncSession, chat_id: str | None = None, user_id: str = "local"
) -> str:
    """Führt den TutorAgent für eine Konversationsrunde aus."""
    agent = create_tutor_agent(db, chat_id, user_id)
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
    chat_id: str | None = None,
    user_id: str = "local",
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
    # chat_id=None: Quiz greift chat-übergreifend auf die gewählten Dokumente zu.
    context = await retrieve_context(
        broad_query,
        source_filter=source_documents,
        n_results=20,
        threshold=None,
        chat_id=None,
        user_id=user_id,
    )
    if not context:
        raise ValueError(
            "Für die ausgewählten Dokumente wurde kein indexierter Inhalt gefunden. "
            "Bitte stelle sicher, dass die Dokumente vollständig verarbeitet wurden."
        )

    doc_label = course_name or ", ".join(source_documents)
    llm = get_llm(temperature=0.3)
    structured_llm = llm.with_structured_output(_QuizSchema)

    # Top-Up-Schleife: so lange (nach-)generieren, bis genug GÜLTIGE Fragen
    # vorliegen. Gleicht aus, dass das LLM oft zu wenige liefert und die
    # Validierung manche verwirft.
    valid: list[dict] = []
    seen: set[str] = set()
    title: str | None = None
    max_rounds = 3

    for round_idx in range(max_rounds):
        need = num_questions - len(valid)
        if need <= 0:
            break
        ask = need + 2  # leicht überanfragen, um Verluste auszugleichen
        user_prompt = (
            f"Erstelle EXAKT {ask} Quizfragen basierend auf den folgenden "
            f"Lernunterlagen ({doc_label}). Liefere wirklich {ask} vollständige Fragen — "
            f"nicht weniger. Multiple-Choice-Fragen haben GENAU 4 Optionen.\n\n"
        )
        if seen:
            sample = list(seen)[:8]
            user_prompt += (
                "Vermeide Wiederholungen dieser bereits gestellten Fragen:\n- "
                + "\n- ".join(sample) + "\n\n"
            )
        user_prompt += f"Lernunterlagen-Kontext:\n{context}"

        try:
            result: _QuizSchema = await structured_llm.ainvoke([
                SystemMessage(content=_QUIZ_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ])
        except Exception as exc:
            logger.error("Quiz-Generierung (Runde %d) fehlgeschlagen: %s", round_idx + 1, exc)
            if valid:
                break  # mit dem Bisherigen weitermachen
            raise RuntimeError("Quiz-Generierung fehlgeschlagen. Bitte später erneut versuchen.")

        title = title or result.title
        for q in result.questions:
            qd = q.model_dump()
            if not _is_valid_quiz_question(qd):
                continue
            key = (qd.get("question") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            valid.append(qd)
            if len(valid) >= num_questions:
                break

    if not valid:
        raise RuntimeError("Keine Fragen generiert. Bitte erneut versuchen.")

    if len(valid) < num_questions:
        logger.info("Quiz: nur %d von %d Fragen erzeugt (Kontext evtl. zu knapp).",
                    len(valid), num_questions)

    return {
        "title": title or f"Quiz: {doc_label}",
        "questions": valid[:num_questions],
    }
