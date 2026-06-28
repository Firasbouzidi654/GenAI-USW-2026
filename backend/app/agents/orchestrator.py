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

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import extract_text_output, get_llm
from app.agents.career_agent import run_career_agent
from app.agents.curriculum_agent import run_curriculum_agent
from app.agents.evaluator_agent import run_evaluator_agent
from app.agents.planner_agent import run_planner_agent
from app.agents.tutor_agent import run_tutor_agent

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


def create_orchestrator(db: AsyncSession, chat_id: str | None = None, user_id: str = "local"):
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
        return await run_tutor_agent(question, db, chat_id, user_id)

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
        system_prompt=_SUPERVISOR_SYSTEM_PROMPT,
    )


async def run_orchestrator(
    message: str, db: AsyncSession, chat_id: str | None = None, user_id: str = "local"
) -> str:
    """Führt den Supervisor-Agent aus. Einstiegspunkt für das Multi-Agent-System.

    Der Supervisor entscheidet selbst, welche Spezial-Agents er aufruft, verkettet
    sie bei Bedarf und liefert eine integrierte Antwort.
    """
    orchestrator = create_orchestrator(db, chat_id, user_id)
    try:
        result = await orchestrator.ainvoke({"messages": [HumanMessage(content=message)]})
        return extract_text_output(result) or "Ich konnte leider keine Antwort generieren."
    except Exception as exc:
        logger.error("Orchestrator fehlgeschlagen: %s", exc)
        return "Der Assistent ist momentan nicht erreichbar. Bitte später erneut versuchen."
