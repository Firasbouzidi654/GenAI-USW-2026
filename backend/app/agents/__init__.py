"""Agent-Paket — vier spezialisierte LangChain-Agents für die Lern-App.

TutorAgent      — beantwortet Fragen aus Lernmaterial (RAG) und generiert Quizze
EvaluatorAgent  — erkennt Wissenslücken aus Quiz-Ergebnissen
PlannerAgent    — erstellt Lernpläne basierend auf Kalender und Deadlines
CareerAgent     — empfiehlt Jobs und Lernpfade basierend auf dem Notenprofil
"""

from app.agents.career_agent import (
    empty_analysis,
    get_ai_career_analysis,
    run_career_agent,
)
from app.agents.evaluator_agent import (
    get_knowledge_gap_analysis,
    run_evaluator_agent,
)
from app.agents.planner_agent import run_planner_agent
from app.agents.tutor_agent import (
    generate_quiz_with_agent,
    run_tutor_agent,
)

__all__ = [
    "run_tutor_agent",
    "generate_quiz_with_agent",
    "run_evaluator_agent",
    "get_knowledge_gap_analysis",
    "run_planner_agent",
    "get_ai_career_analysis",
    "run_career_agent",
    "empty_analysis",
]
