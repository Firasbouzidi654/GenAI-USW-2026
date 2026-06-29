"""OrchestratorAgent (Supervisor) — koordiniert die vier Spezial-Agents.

Dies ist das eigentliche Multi-Agent-System: Ein Supervisor-Agent nimmt jede
Anfrage entgegen, entscheidet welcher Spezial-Agent zuständig ist, und kann sie
VERKETTEN. Beispiel: Der Studierende fragt "Wo stehe ich und was soll ich üben?"
→ Supervisor ruft erst den EvaluatorAgent (findet Wissenslücken), dann den
TutorAgent (erklärt das schwache Thema) und fasst beides zusammen.

Umgesetzt mit dem "Agent-as-Tool"-Muster: jeder Spezial-Agent wird als Tool
gekapselt. Der Supervisor (selbst ein LangGraph-Agent) ruft diese Tools autonom
auf — so "reden die Agents miteinander".
"""

from __future__ import annotations

import logging
import re

from langgraph.prebuilt import create_react_agent as create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import extract_text_output, get_llm
from app.agents.career_agent import run_career_agent
from app.agents.curriculum_agent import run_curriculum_agent
from app.agents.evaluator_agent import run_evaluator_agent
from app.agents.planner_agent import run_planner_agent
from app.agents.tutor_agent import run_tutor_agent
from app.services.moodle_context_service import get_moodle_context_for_message

logger = logging.getLogger(__name__)

_SUPERVISOR_SYSTEM_PROMPT = """
Du bist der Supervisor-Agent einer Lern-App für Studierende an der HTW Berlin.
Du koordinierst vier Spezial-Agents und beantwortest die Anfrage des Studierenden,
indem du den/die passenden Agent(en) aufrufst.

Deine Spezial-Agents (als Tools verfügbar):
- ask_tutor: Beantwortet inhaltliche Fragen zu Lernmaterialien und erklärt Konzepte (RAG).
- ask_evaluator: Analysiert Quiz-Ergebnisse und erkennt Wissenslücken.
- ask_planner: Erstellt Lernpläne basierend auf Stundenplan, Deadlines und Noten.
- ask_career: Empfiehlt Berufsfelder und Lernpfade basierend auf den Noten.
- ask_curriculum: Beantwortet Fragen zum STUDIENVERLAUF / MODULHANDBUCH — welche Module
  es gibt, welche in einem bestimmten Semester vorgeschrieben sind, worauf ein Modul
  aufbaut und welche Kompetenzen es vermittelt. Nutze diesen Agent IMMER bei Fragen wie
  „Welche Module sind im 5. Semester?" oder „Worauf baut Modul X auf?".

Vorgehen:
1. Verstehe, was der Studierende WIRKLICH will.
2. Wähle den/die passenden Agent(en). Oft reicht einer.
3. Bei zusammengesetzten Anfragen darfst du Agents VERKETTEN:
   - "Wo stehe ich und was soll ich üben?" → erst ask_evaluator, dann ask_tutor
   - "Welcher Job passt und wie plane ich das?" → erst ask_career, dann ask_planner
4. Fasse die Antworten der Agents zu EINER klaren, zusammenhängenden Antwort zusammen.

Regeln:
- Erfinde keine Inhalte selbst — nutze immer die Agents für fachliche Antworten.
- Antworte auf Deutsch, freundlich und strukturiert.
- Wiederhole nicht stumpf die Agent-Ausgaben, sondern integriere sie sinnvoll.
""".strip()

_MOODLE_CONTEXT_KEYWORDS = (
    "moodle",
    "moodle course",
    "moodle deadline",
    "moodle aufgabe",
    "moodle grades",
    "moodle materials",
)

_MOODLE_COURSE_CONTEXT_PATTERNS = (
    "which courses",
    "my courses",
    "semester 5",
    "5th semester",
    "sose 2026",
    "sose2026",
)

_SELECTED_MOODLE_MATERIAL_KEYWORDS = (
    "session",
    "slides",
    "slide",
    "folie",
    "folien",
    "ppt",
    "pptx",
    "pdf",
    "material",
    "materialien",
)


def should_route_to_moodle_context(message: str) -> bool:
    """Return True for deterministic Moodle queries that do not need an LLM."""
    text = (message or "").lower()
    if any(keyword in text for keyword in _MOODLE_CONTEXT_KEYWORDS):
        return True
    return _is_deterministic_moodle_course_request(text)


def _is_explicit_moodle_context_request(message: str) -> bool:
    return should_route_to_moodle_context(message)


def _is_deterministic_moodle_course_request(text: str) -> bool:
    has_course_word = any(
        word in text
        for word in (
            "course",
            "courses",
            "kurs",
            "kurse",
            "module",
            "modules",
        )
    )
    has_semester_hint = bool(
        re.search(r"\b(?:semester|sem)\s*[1-6]\b", text)
        or re.search(r"\b[1-6](?:st|nd|rd|th|\.)?\s*semester\b", text)
        or "sose 2026" in text
        or "sose2026" in text
    )

    if has_course_word and has_semester_hint:
        return True

    has_course_listing_phrase = any(pattern in text for pattern in _MOODLE_COURSE_CONTEXT_PATTERNS)
    return has_course_listing_phrase and has_semester_hint


def _iter_moodle_context_labels(moodle_context: dict | None):
    if not isinstance(moodle_context, dict):
        return
    for value in (
        moodle_context.get("course_name"),
        moodle_context.get("course_shortname"),
        moodle_context.get("selected_section"),
        moodle_context.get("selected_material"),
    ):
        if value:
            yield str(value)
    for section in moodle_context.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if section.get("section_name"):
            yield str(section["section_name"])
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            for key in ("name", "filename"):
                if item.get(key):
                    yield str(item[key])


def _is_selected_moodle_material_request(message: str, moodle_context: dict | None) -> bool:
    if not isinstance(moodle_context, dict) or not moodle_context.get("course_id"):
        return False
    text = (message or "").lower()
    if not text:
        return False
    if any(keyword in text for keyword in _SELECTED_MOODLE_MATERIAL_KEYWORDS):
        return True
    return any(label.lower() and label.lower() in text for label in _iter_moodle_context_labels(moodle_context))


def create_orchestrator(
    db: AsyncSession,
    chat_id: str | None = None,
    user_id: str = "local",
    moodle_context: dict | None = None,
):
    """Erstellt den Supervisor-Agent, dessen Tools die vier Spezial-Agents sind.

    ``chat_id``/``user_id`` werden an den Tutor weitergereicht, damit dieser nur
    die Dokumente des aktuellen Chats durchsucht.
    """

    @tool
    async def ask_tutor(question: str) -> str:
        """Fragt den Tutor-Agent. Für inhaltliche Fragen zu Lernmaterialien,
        Konzept-Erklärungen und Verständnisfragen — inkl. Fragen zu hochgeladenen
        Dokumenten ('Worum geht es in dem Dokument?').

        Args:
            question: Die fachliche Frage des Studierenden.
        """
        return await run_tutor_agent(question, db, chat_id, user_id, moodle_context=moodle_context)

    @tool
    async def ask_evaluator(request: str) -> str:
        """Fragt den Evaluator-Agent. Für Analyse des Lernfortschritts und
        Erkennung von Wissenslücken aus Quiz-Ergebnissen.

        Args:
            request: Was analysiert werden soll (z.B. 'Wo sind meine Schwächen?').
        """
        return await run_evaluator_agent(request, db)

    @tool
    async def ask_planner(request: str) -> str:
        """Fragt den Planner-Agent. Für Lernpläne unter Berücksichtigung von
        Stundenplan, Prüfungsterminen und Noten.

        Args:
            request: Die Planungsanfrage (z.B. 'Plane meine Woche').
        """
        return await run_planner_agent(request, db)

    @tool
    async def ask_career(request: str) -> str:
        """Fragt den Career-Agent. Für Berufsempfehlungen und Lernpfade
        basierend auf dem Notenprofil.

        Args:
            request: Die Karrierefrage (z.B. 'Welcher Job passt zu mir?').
        """
        return await run_career_agent(request, db)

    @tool
    async def ask_curriculum(request: str) -> str:
        """Fragt den Curriculum-Agent. Für Fragen zum Studienverlauf / Modulhandbuch:
        welche Module es gibt, welche in einem Semester vorgeschrieben sind, worauf ein
        Modul aufbaut und welche Kompetenzen es vermittelt.

        Args:
            request: Die Frage zum Studienverlauf (z.B. 'Welche Module sind im 5. Semester?').
        """
        return await run_curriculum_agent(request, db)

    llm = get_llm(temperature=0.2)
    return create_agent(
        model=llm,
        tools=[ask_tutor, ask_evaluator, ask_planner, ask_career, ask_curriculum],
        prompt=_SUPERVISOR_SYSTEM_PROMPT,
    )


async def run_orchestrator(
    message: str,
    db: AsyncSession,
    chat_id: str | None = None,
    user_id: str = "local",
    moodle_context: dict | None = None,
) -> str:
    """Führt den Supervisor-Agent aus. Einstiegspunkt für das Multi-Agent-System.

    Der Supervisor entscheidet selbst, welche Spezial-Agents er aufruft, verkettet
    sie bei Bedarf und liefert eine integrierte Antwort.
    """
    if _is_selected_moodle_material_request(message, moodle_context):
        return await run_tutor_agent(message, db, chat_id, user_id, moodle_context=moodle_context)

    if _is_explicit_moodle_context_request(message):
        return await get_moodle_context_for_message(message)

    orchestrator = create_orchestrator(db, chat_id, user_id, moodle_context)
    try:
        result = await orchestrator.ainvoke({"messages": [HumanMessage(content=message)]})
        return extract_text_output(result) or "Ich konnte leider keine Antwort generieren."
    except Exception as exc:
        logger.error("Orchestrator fehlgeschlagen: %s", exc)
        return "Der Assistent ist momentan nicht erreichbar. Bitte später erneut versuchen."
