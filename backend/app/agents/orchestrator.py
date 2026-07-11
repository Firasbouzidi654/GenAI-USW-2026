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

import asyncio
import logging
import re

from langgraph.prebuilt import create_react_agent as create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import extract_text_output, get_llm, run_agent_with_model_fallback
from app.agents.career_agent import run_career_agent
from app.agents.curriculum_agent import run_curriculum_agent
from app.agents.evaluator_agent import run_evaluator_agent
from app.agents.planner_agent import run_planner_agent
from app.agents.tutor_agent import run_tutor_agent
from app.core.config import settings
from app.observability import trace_bus
from app.services.moodle_context_service import get_moodle_context_for_message

logger = logging.getLogger(__name__)

_SUPERVISOR_SYSTEM_PROMPT = """
Du bist der Supervisor-Agent einer Lern-App für Studierende an der HTW Berlin.
Du koordinierst vier Spezial-Agents und beantwortest die Anfrage des Studierenden,
indem du den/die passenden Agent(en) aufrufst.

WICHTIGSTE REGEL — WISSENSQUELLE:
Fachliche/inhaltliche Fragen (Erklärungen, Konzepte, Definitionen, „Was ist X?",
„Erkläre mir Y") werden AUSSCHLIESSLICH aus MOODLE beantwortet. Rufe dafür IMMER
ask_moodle auf. Beantworte solche Fragen NIEMALS aus deinem eigenen Wissen und nutze
für sie NICHT ask_tutor. Wenn Moodle dazu nichts hergibt, sage das ehrlich —
erfinde nichts und ergänze nichts aus Allgemeinwissen.

Deine Spezial-Agents (als Tools verfügbar):
- ask_moodle: DEFAULT für ALLE fachlichen/inhaltlichen Fragen. Erkennt automatisch das
  passende Moodle-Modul, indiziert dessen Material und antwortet NUR daraus.
- ask_tutor: NUR wenn der Studierende sich ausdrücklich auf ein SELBST HOCHGELADENES
  Dokument in diesem Chat bezieht ("im hochgeladenen PDF", "in meinem Dokument").
- ask_evaluator: Analysiert Quiz-Ergebnisse und erkennt Wissenslücken.
- ask_planner: Erstellt Lernpläne basierend auf Stundenplan, Deadlines und Noten.
- ask_career: Empfiehlt Berufsfelder und Lernpfade basierend auf den Noten.
- ask_curriculum: Fragen zum STUDIENVERLAUF / MODULHANDBUCH — welche Module es gibt,
  welche in einem Semester vorgeschrieben sind, worauf ein Modul aufbaut. Nutze diesen
  Agent bei Fragen wie „Welche Module sind im 5. Semester?".

Vorgehen:
1. Verstehe, was der Studierende WIRKLICH will.
2. Ist es eine fachliche Wissensfrage → ask_moodle. Sonst den passenden Spezial-Agent.
3. Bei zusammengesetzten Anfragen darfst du Agents VERKETTEN.
4. Fasse die Antworten der Agents zu EINER klaren Antwort zusammen — OHNE eigenes
   Wissen hinzuzufügen. Gib nur wieder, was die Agents/Moodle liefern.

Regeln:
- Erfinde keine Inhalte selbst — nutze immer die Agents für fachliche Antworten.
- Antworte auf Deutsch, freundlich und strukturiert.
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


_QUIZ_ACTION_WORDS = (
    "erstell", "generier", "mach", "erzeug", "gib mir", "gibt mir", "starte",
    "möchte", "moechte", "will", "brauche", "bau", "create", "make", "generate",
)


def detect_quiz_request(message: str) -> int | None:
    """Erkennt eine Quiz-Erstellungs-Absicht und liefert die gewünschte Fragenanzahl.

    Rückgabe: None = keine Quiz-Anfrage; >0 = explizit gewünschte Anzahl;
    0 = keine Zahl genannt → Anzahl automatisch aus dem Materialumfang ableiten.
    Nur wenn „quiz" + ein Aktionswort (oder „teste mich") vorkommt — vermeidet
    Fehlauslöser bei Fragen wie „Was ist ein Quiz?".
    """
    text = (message or "").lower()
    is_quiz = (
        ("quiz" in text and any(w in text for w in _QUIZ_ACTION_WORDS))
        or "teste mich" in text
        or "test me" in text
        or "prüfe mein wissen" in text
        or "pruefe mein wissen" in text
    )
    if not is_quiz:
        return None
    m = re.search(r"(\d+)\s*(?:frag|quiz|question|aufgab)", text) or re.search(r"\b(\d{1,2})\b", text)
    if m:
        return max(1, min(20, int(m.group(1))))
    return 0  # automatisch anhand des Stoffumfangs entscheiden


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
    llm=None,
):
    """Erstellt den Supervisor-Agent, dessen Tools die vier Spezial-Agents sind.

    ``chat_id``/``user_id`` werden an den Tutor weitergereicht, damit dieser nur
    die Dokumente des aktuellen Chats durchsucht.
    """

    @tool
    async def ask_tutor(question: str) -> str:
        """Fragt den Tutor-Agent. Für inhaltliche Fragen zu HOCHGELADENEN Lernmaterialien,
        Konzept-Erklärungen und Verständnisfragen ('Worum geht es in dem Dokument?').

        Args:
            question: Die fachliche Frage des Studierenden.
        """
        trace_bus.publish("agent_start", "tutor", "Tutor-Agent (RAG)", question[:160])
        trace_bus.add_tool("Tutor-Agent (hochgeladene Dokumente)")
        out = await run_tutor_agent(question, db, chat_id, user_id, moodle_context=moodle_context)
        trace_bus.publish("agent_end", "tutor", "Tutor-Agent fertig", out[:160], status="ok")
        return out

    @tool
    async def ask_moodle(question: str) -> str:
        """Beantwortet eine inhaltliche Frage aus MOODLE-Materialien, OHNE dass etwas
        hochgeladen werden muss. Erkennt automatisch das passende Moodle-Modul zur Frage,
        indiziert dessen Material einmalig und antwortet daraus. Nutze dies bei fachlichen
        Fragen zu einem Modul/Kurs, wenn KEINE eigenen Dokumente hochgeladen wurden.

        Args:
            question: Die inhaltliche Frage des Studierenden.
        """
        from app.services.moodle_qa_service import answer_from_moodle

        trace_bus.publish("agent_start", "moodle", "Moodle-QA", question[:160])
        trace_bus.add_tool("Moodle-QA (Moodle-Kursmaterial)")
        out = await answer_from_moodle(question, chat_id, user_id)
        trace_bus.publish("agent_end", "moodle", "Moodle-QA fertig", out[:160], status="ok")
        return out

    @tool
    async def ask_evaluator(request: str) -> str:
        """Fragt den Evaluator-Agent. Für Analyse des Lernfortschritts und
        Erkennung von Wissenslücken aus Quiz-Ergebnissen.

        Args:
            request: Was analysiert werden soll (z.B. 'Wo sind meine Schwächen?').
        """
        trace_bus.publish("agent_start", "evaluator", "Evaluator-Agent", request[:160])
        trace_bus.add_tool("Evaluator-Agent (Quiz-Ergebnisse)")
        out = await run_evaluator_agent(request, db)
        trace_bus.publish("agent_end", "evaluator", "Evaluator-Agent fertig", out[:160], status="ok")
        return out

    @tool
    async def ask_planner(request: str) -> str:
        """Fragt den Planner-Agent. Für Lernpläne unter Berücksichtigung von
        Stundenplan, Prüfungsterminen und Noten.

        Args:
            request: Die Planungsanfrage (z.B. 'Plane meine Woche').
        """
        trace_bus.publish("agent_start", "planner", "Planner-Agent", request[:160])
        trace_bus.add_tool("Planner-Agent (Stundenplan/Deadlines)")
        out = await run_planner_agent(request, db)
        trace_bus.publish("agent_end", "planner", "Planner-Agent fertig", out[:160], status="ok")
        return out

    @tool
    async def ask_career(request: str) -> str:
        """Fragt den Career-Agent. Für Berufsempfehlungen und Lernpfade
        basierend auf dem Notenprofil.

        Args:
            request: Die Karrierefrage (z.B. 'Welcher Job passt zu mir?').
        """
        trace_bus.publish("agent_start", "career", "Career-Agent", request[:160])
        trace_bus.add_tool("Career-Agent (Notenprofil)")
        out = await run_career_agent(request, db)
        trace_bus.publish("agent_end", "career", "Career-Agent fertig", out[:160], status="ok")
        return out

    @tool
    async def ask_curriculum(request: str) -> str:
        """Fragt den Curriculum-Agent. Für Fragen zum Studienverlauf / Modulhandbuch:
        welche Module es gibt, welche in einem Semester vorgeschrieben sind, worauf ein
        Modul aufbaut und welche Kompetenzen es vermittelt.

        Args:
            request: Die Frage zum Studienverlauf (z.B. 'Welche Module sind im 5. Semester?').
        """
        trace_bus.publish("agent_start", "curriculum", "Curriculum-Agent", request[:160])
        trace_bus.add_tool("Curriculum-Agent (Modulhandbuch)")
        out = await run_curriculum_agent(request, db)
        trace_bus.publish("agent_end", "curriculum", "Curriculum-Agent fertig", out[:160], status="ok")
        return out

    llm = llm or get_llm(temperature=0.2)
    return create_agent(
        model=llm,
        tools=[ask_tutor, ask_moodle, ask_evaluator, ask_planner, ask_career, ask_curriculum],
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
    trace_bus.publish("agent_start", "orchestrator", "Orchestrator", message[:160])

    # Quiz-Erstellung: deterministisch erkennen und ein ECHTES Quiz (aus Moodle) bauen,
    # das im Quiz-Tab geöffnet werden kann — statt nur Fragen als Chattext.
    num_questions = detect_quiz_request(message)
    if num_questions is not None:
        trace_bus.publish("route", "orchestrator", f"Direkt-Routing → Quiz erstellen ({num_questions} Fragen)", "", status="ok")
        from app.services.moodle_qa_service import create_quiz_from_moodle

        _quiz, text = await create_quiz_from_moodle(message, num_questions, db, user_id)
        trace_bus.publish("agent_end", "orchestrator", "Orchestrator fertig", text[:160], status="ok")
        return text

    if _is_selected_moodle_material_request(message, moodle_context):
        trace_bus.publish("route", "orchestrator", "Direkt-Routing → Moodle-Material (Tutor)", "", status="ok")
        trace_bus.add_tool("Moodle-Material (ausgewählt)")
        out = await run_tutor_agent(message, db, chat_id, user_id, moodle_context=moodle_context)
        trace_bus.publish("agent_end", "orchestrator", "Orchestrator fertig", out[:160], status="ok")
        return out

    if _is_explicit_moodle_context_request(message):
        trace_bus.publish("route", "orchestrator", "Direkt-Routing → Moodle-Kontext (ohne LLM)", "", status="ok")
        trace_bus.add_tool("Moodle-Kontext (Kurse/Deadlines/Noten)")
        out = await get_moodle_context_for_message(message)
        trace_bus.publish("agent_end", "orchestrator", "Orchestrator fertig", out[:160], status="ok")
        return out

    # LLM-Orchestrator NUR über Gemini-Modelle (Tool-Calling ist auf Gemini zuverlässig,
    # auf Groq/Llama fehlerhaft → 'tool_use_failed'/Hänger). Die ganze Gemini-Kette wird
    # durchprobiert; erst wenn ALLE Gemini-Modelle ausfallen (z.B. Tages-Quota erschöpft),
    # greift der Moodle-Fallback (nur einfache LLM-Calls, die auch Groq beherrscht) —
    # passend zur Vorgabe „Antworten nur aus Moodle".
    last_exc: Exception | None = None
    for model_name in settings.gemini_model_list:
        try:
            agent = create_orchestrator(
                db, chat_id, user_id, moodle_context,
                llm=get_llm(model=model_name, temperature=0.2),
            )
            result = await asyncio.wait_for(
                agent.ainvoke({"messages": [HumanMessage(content=message)]}),
                timeout=45,
            )
            out = extract_text_output(result)
            if out:
                trace_bus.publish("agent_end", "orchestrator", f"Orchestrator fertig ({model_name})", out[:160], status="ok")
                return out
            last_exc = RuntimeError("leere Antwort")
        except Exception as exc:
            last_exc = exc
            logger.warning("Gemini-Modell '%s' im Orchestrator fehlgeschlagen: %s", model_name, exc)
            continue

    # Alle Gemini-Modelle fehlgeschlagen → Moodle-Fallback (Groq-tauglich).
    trace_bus.publish(
        "route", "orchestrator", "Fallback → Moodle-QA (alle Gemini-Modelle erschöpft)",
        str(last_exc)[:140], status="warn",
    )
    from app.services.moodle_qa_service import answer_from_moodle

    trace_bus.add_tool("Moodle-QA (Moodle-Kursmaterial)")
    try:
        out = await answer_from_moodle(message, chat_id, user_id)
    except Exception as exc2:
        logger.error("Moodle-Fallback fehlgeschlagen: %s", exc2)
        trace_bus.publish("error", "orchestrator", "Moodle-Fallback-Fehler", str(exc2)[:140], status="error")
        return "Der Assistent ist momentan nicht erreichbar. Bitte später erneut versuchen."
    trace_bus.publish("agent_end", "orchestrator", "Orchestrator fertig", out[:160], status="ok")
    return out
