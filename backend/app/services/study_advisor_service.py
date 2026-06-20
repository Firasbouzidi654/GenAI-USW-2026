"""Study Advisor Service — delegiert Lernplan-Anfragen an den PlannerAgent."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.planner_agent import run_planner_agent


async def get_study_advice(message: str, db: AsyncSession) -> str:
    """Gibt Lernplan-Empfehlungen via PlannerAgent zurück.

    Der PlannerAgent holt selbstständig Kalender-Events und Deadlines aus der DB
    und erstellt einen personalisierten Lernplan.
    """
    return await run_planner_agent(message, db)
