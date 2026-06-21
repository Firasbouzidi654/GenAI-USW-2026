"""EvaluatorAgent — erkennt Wissenslücken aus Quiz-Ergebnissen und gibt Empfehlungen.

Nutzt LangChain 1.x `create_agent`. Der Agent ruft selbstständig mehrere Tools
auf, um ein vollständiges Bild des Lernfortschritts zu bekommen.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import extract_text_output, get_llm
from app.models.attempt_answer import AttemptAnswer
from app.models.curriculum import CurriculumModule
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_question import QuizQuestion

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
Du bist ein Evaluator-Agent für Studierende. Du analysierst Quiz-Ergebnisse und
identifizierst Wissenslücken.

Du hast Zugriff auf:
- Gesamtstatistiken (Durchschnittswert, Anzahl Versuche, Trend)
- Schwache Fragen (unter 60 % richtig beantwortet)
- Fragetyp-Analyse (Multiple-Choice vs. Wahr/Falsch)
- Letzte Quiz-Versuche mit Ergebnissen
- Das Modulhandbuch (Vorgängermodule): zu jedem Modul, auf welchen Modulen es aufbaut

Vorgehen:
1. Rufe ALLE relevanten Tools auf, um ein vollständiges Bild zu bekommen
2. Erkenne Muster in den Fehlern (z.B. immer falsch bei Faktenfragen)
3. Für JEDES schwache Modul/Thema: rufe find_prerequisites mit dem Modul-/Quiz-Namen auf.
   Gibt es Vorgängermodule, EMPFIEHL ausdrücklich, zuerst diese Vorgänger zu wiederholen
   ("Lücke an der Wurzel beheben"). Gibt es kein Modulhandbuch, lass diesen Schritt aus.
4. Priorisiere Schwachstellen nach Häufigkeit und Wichtigkeit
5. Gib 3–5 konkrete, handlungsorientierte Empfehlungen

Antworte auf Deutsch. Nutze klare Struktur mit Abschnitten und Aufzählungen.
Sei konstruktiv und motivierend.
""".strip()


def _match_module(modules: list, name: str):
    """Findet das am besten passende Curriculum-Modul zu einem (Teil-)Namen."""
    q = (name or "").strip().lower()
    if not q:
        return None
    for m in modules:
        if q == m.name.lower():
            return m
    for m in modules:
        if q in m.name.lower() or m.name.lower() in q:
            return m
    q_words = set(q.split())
    best, best_overlap = None, 0
    for m in modules:
        overlap = len(q_words & set(m.name.lower().split()))
        if overlap > best_overlap:
            best, best_overlap = m, overlap
    return best if best_overlap else None


def create_evaluator_agent(db: AsyncSession):
    """Erstellt einen EvaluatorAgent (LangGraph CompiledStateGraph)."""

    @tool
    async def get_overall_quiz_statistics() -> str:
        """Gibt Gesamtstatistiken zu allen Quiz-Versuchen zurück:
        Anzahl Versuche, Durchschnittsnote, Verbesserungstrend."""
        try:
            result = await db.execute(select(QuizAttempt).order_by(QuizAttempt.created_at))
            attempts = result.scalars().all()
            if not attempts:
                return "Noch keine Quiz-Versuche vorhanden."

            total = len(attempts)
            scores = [a.score / a.total_questions * 100 for a in attempts if a.total_questions > 0]
            avg = round(sum(scores) / len(scores), 1) if scores else 0

            third = max(1, total // 3)
            early_avg = round(sum(scores[:third]) / third, 1) if scores[:third] else 0
            recent_avg = round(sum(scores[-third:]) / third, 1) if scores[-third:] else 0
            trend = "verbessernd" if recent_avg > early_avg + 5 else (
                "verschlechternd" if recent_avg < early_avg - 5 else "stabil"
            )

            return json.dumps({
                "total_attempts": total,
                "average_score_percent": avg,
                "trend": trend,
                "early_average": early_avg,
                "recent_average": recent_avg,
            }, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Statistik-Abfrage fehlgeschlagen: %s", exc)
            return "Statistiken konnten nicht abgerufen werden."

    @tool
    async def get_weak_questions(limit: int = 10) -> str:
        """Gibt die Fragen zurück, bei denen der Studierende am häufigsten Fehler macht.
        Sortiert nach Fehlerrate (schlechteste zuerst).

        Args:
            limit: Maximale Anzahl schwacher Fragen (Standard: 10)
        """
        try:
            answers_result = await db.execute(select(AttemptAnswer))
            all_answers = answers_result.scalars().all()
            if not all_answers:
                return "Noch keine Antworten vorhanden."

            stats: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
            for ans in all_answers:
                stats[ans.question_id]["total"] += 1
                if ans.is_correct:
                    stats[ans.question_id]["correct"] += 1

            question_ids = list(stats.keys())
            q_result = await db.execute(
                select(QuizQuestion).where(QuizQuestion.id.in_(question_ids))
            )
            questions_by_id = {q.id: q for q in q_result.scalars().all()}

            weak = []
            for qid, counts in stats.items():
                q = questions_by_id.get(qid)
                if q is None:
                    continue
                rate = counts["correct"] / counts["total"] * 100 if counts["total"] > 0 else 0
                if rate < 60:
                    weak.append({
                        "question_text": q.question_text,
                        "question_type": q.question_type,
                        "success_rate_percent": round(rate, 1),
                        "attempts": counts["total"],
                    })

            weak.sort(key=lambda x: x["success_rate_percent"])
            if not weak:
                return "Keine schwachen Fragen gefunden — sehr gut!"
            return json.dumps(weak[:limit], ensure_ascii=False)
        except Exception as exc:
            logger.warning("Schwache-Fragen-Abfrage fehlgeschlagen: %s", exc)
            return "Schwache Fragen konnten nicht abgerufen werden."

    @tool
    async def get_recent_attempts(limit: int = 5) -> str:
        """Gibt die letzten Quiz-Versuche mit Quiz-Titel und Ergebnis zurück.

        Args:
            limit: Anzahl der letzten Versuche (Standard: 5)
        """
        try:
            attempt_result = await db.execute(
                select(QuizAttempt).order_by(QuizAttempt.created_at.desc()).limit(limit)
            )
            attempts = attempt_result.scalars().all()
            if not attempts:
                return "Noch keine Versuche vorhanden."

            quiz_ids = list({a.quiz_id for a in attempts})
            quiz_result = await db.execute(select(Quiz).where(Quiz.id.in_(quiz_ids)))
            quizzes_by_id = {q.id: q for q in quiz_result.scalars().all()}

            output = []
            for a in attempts:
                quiz = quizzes_by_id.get(a.quiz_id)
                pct = round(a.score / a.total_questions * 100, 1) if a.total_questions > 0 else 0
                output.append({
                    "quiz_title": quiz.title if quiz else f"Quiz #{a.quiz_id}",
                    "score": a.score,
                    "total": a.total_questions,
                    "percentage": pct,
                    "date": a.created_at.strftime("%d.%m.%Y %H:%M"),
                })
            return json.dumps(output, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Letzte-Versuche-Abfrage fehlgeschlagen: %s", exc)
            return "Letzte Versuche konnten nicht abgerufen werden."

    @tool
    async def get_question_type_breakdown() -> str:
        """Analysiert Erfolgsrate aufgeteilt nach Fragetyp (MC = Multiple Choice vs. TF = Wahr/Falsch)."""
        try:
            answers_result = await db.execute(select(AttemptAnswer))
            all_answers = answers_result.scalars().all()
            if not all_answers:
                return "Keine Antwortdaten vorhanden."

            question_ids = list({a.question_id for a in all_answers})
            q_result = await db.execute(
                select(QuizQuestion).where(QuizQuestion.id.in_(question_ids))
            )
            type_by_id = {q.id: q.question_type for q in q_result.scalars().all()}

            breakdown: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
            for ans in all_answers:
                qtype = type_by_id.get(ans.question_id, "UNKNOWN")
                breakdown[qtype]["total"] += 1
                if ans.is_correct:
                    breakdown[qtype]["correct"] += 1

            result = {}
            for qtype, counts in breakdown.items():
                rate = counts["correct"] / counts["total"] * 100 if counts["total"] > 0 else 0
                result[qtype] = {
                    "success_rate_percent": round(rate, 1),
                    "total_answers": counts["total"],
                }
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Fragetyp-Analyse fehlgeschlagen: %s", exc)
            return "Fragetyp-Analyse konnte nicht durchgeführt werden."

    @tool
    async def find_prerequisites(module_name: str) -> str:
        """Schlägt im Modulhandbuch nach, auf welchen VORGÄNGERMODULEN ein Modul aufbaut.
        Nutze dies für jedes schwache Modul/Thema, um zu empfehlen, welche Vorgänger
        der Studierende zuerst wiederholen sollte.

        Args:
            module_name: Name des (schwachen) Moduls oder Quiz-Themas.
        """
        try:
            modules = (await db.execute(select(CurriculumModule))).scalars().all()
        except Exception:
            modules = []
        if not modules:
            return "Kein Modulhandbuch hinterlegt — Vorgängermodule sind nicht verfügbar."
        m = _match_module(modules, module_name)
        if m is None:
            return f"Kein passendes Modul zu '{module_name}' im Modulhandbuch gefunden."
        if not m.prerequisites:
            return f"'{m.name}' hat laut Modulhandbuch keine Vorgängermodule."
        by_name = {x.name.lower(): x for x in modules}
        lines = []
        for p in m.prerequisites:
            pm = by_name.get(p.lower())
            desc = f" — {pm.description}" if pm and pm.description else ""
            lines.append(f"- {p}{desc}")
        return f"'{m.name}' baut auf folgenden Vorgängermodulen auf:\n" + "\n".join(lines)

    @tool
    async def list_curriculum_modules() -> str:
        """Listet die Module aus dem Modulhandbuch (Namen). Hilft, schwache Themen den
        richtigen Modulnamen zuzuordnen."""
        try:
            modules = (await db.execute(select(CurriculumModule).order_by(CurriculumModule.name))).scalars().all()
        except Exception:
            modules = []
        if not modules:
            return "Kein Modulhandbuch hinterlegt."
        return "Module im Modulhandbuch:\n" + "\n".join(f"- {m.name}" for m in modules)

    llm = get_llm(temperature=0.3)
    return create_agent(
        model=llm,
        tools=[
            get_overall_quiz_statistics,
            get_weak_questions,
            get_recent_attempts,
            get_question_type_breakdown,
            find_prerequisites,
            list_curriculum_modules,
        ],
        system_prompt=_SYSTEM_PROMPT,
    )


async def run_evaluator_agent(message: str, db: AsyncSession) -> str:
    """Führt den EvaluatorAgent aus und gibt eine Wissenslücken-Analyse zurück."""
    agent = create_evaluator_agent(db)
    try:
        result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
        return extract_text_output(result) or "Die Analyse konnte nicht abgeschlossen werden."
    except Exception as exc:
        logger.error("EvaluatorAgent fehlgeschlagen: %s", exc)
        return "Der Evaluator ist momentan nicht erreichbar. Bitte später erneut versuchen."


async def get_knowledge_gap_analysis(db: AsyncSession) -> str:
    """Vollständige Wissenslücken-Analyse aller Quiz-Ergebnisse."""
    prompt = (
        "Analysiere meinen gesamten Lernfortschritt. "
        "Sammle alle verfügbaren Daten und erstelle eine detaillierte Analyse meiner "
        "Wissenslücken mit konkreten Empfehlungen, was ich als nächstes üben soll."
    )
    return await run_evaluator_agent(prompt, db)
