"""CurriculumAgent — beantwortet Fragen zum Studienverlauf / Modulhandbuch.

Greift auf die strukturierte Tabelle ``curriculum_modules`` zu (befüllt aus dem
hochgeladenen Modulhandbuch) und beantwortet Fragen wie „Welche Module sind im
5. Semester vorgeschrieben?", „Worauf baut Modul X auf?" oder „Was lerne ich in Y?".

Wichtig: Anders als der TutorAgent (RAG über hochgeladene Lerndokumente) nutzt dieser
Agent die strukturierten Modul-Daten — denn das Modulhandbuch landet beim Upload in
dieser Tabelle und nicht im Vektor-Store.
"""

from __future__ import annotations

import logging
import re

from langgraph.prebuilt import create_react_agent as create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import extract_text_output, get_llm
from app.models.curriculum import CurriculumModule

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
Du bist der Curriculum-Agent einer Lern-App für Studierende an der HTW Berlin.
Du beantwortest Fragen zum Studienverlauf anhand des hochgeladenen Modulhandbuchs.

Du hast Zugriff auf die strukturierten Moduldaten (Name, Semester, Pflicht/Wahlpflicht,
Vorgängermodule, Kompetenzen) über deine Tools. Nutze IMMER die Tools — erfinde keine Module.

Vorgehen:
1. Bei Fragen nach einem bestimmten Semester (z.B. „5. Semester"): rufe
   modules_by_semester mit der Semesterzahl auf und liste die Module auf.
2. Bei Fragen zu einem einzelnen Modul: rufe module_details auf.
3. Bei allgemeinem Überblick: rufe list_all_modules auf.

Wichtig — Pflicht vs. Wahlpflicht:
- „Welche Module MUSS ich belegen / sind VORGESCHRIEBEN / sind PFLICHT?" → das sind die
  PFLICHTMODULE. Nenne sie zuerst und deutlich getrennt von den Wahlpflichtmodulen.
- Wahlpflichtmodule sind WÄHLBARE Optionen — nenne sie als solche, nicht als Pflicht.
- Das Tool liefert die Einordnung (Pflicht/Wahlpflicht) bereits mit — übernimm sie exakt
  und erfinde keine eigene Zuordnung.

Regeln:
- Ist gar kein Modulhandbuch hinterlegt, sage das klar und bitte um den Upload im Profil.
- Antworte auf Deutsch, strukturiert mit Aufzählungen.
""".strip()


def _digits(value: str | None) -> set[str]:
    return set(re.findall(r"\d+", value or ""))


def create_curriculum_agent(db: AsyncSession):
    """Erstellt einen CurriculumAgent (LangGraph CompiledStateGraph)."""

    @tool
    async def modules_by_semester(semester: str) -> str:
        """Listet die Module, die einem bestimmten Fachsemester zugeordnet sind.

        Args:
            semester: Die Semesterzahl, z.B. '5'.
        """
        target = _digits(semester)
        if not target:
            return "Bitte eine konkrete Semesterzahl angeben (z.B. 5)."
        try:
            modules = (await db.execute(
                select(CurriculumModule).order_by(CurriculumModule.name)
            )).scalars().all()
        except Exception:
            modules = []
        if not modules:
            return "Kein Modulhandbuch hinterlegt — bitte im Profil hochladen."
        hits = [m for m in modules if _digits(m.semester) & target]
        if not hits:
            return (
                f"Keine Module mit Semesterangabe {sorted(target)} im Modulhandbuch gefunden."
            )
        sem = sorted(target)[0]
        pflicht = [m for m in hits if (m.module_type or "").lower().startswith("pflicht")]
        wahlpflicht = [m for m in hits if (m.module_type or "").lower().startswith("wahlpflicht")]
        sonstige = [m for m in hits if m not in pflicht and m not in wahlpflicht]

        def _fmt(items):
            out = []
            for m in items:
                desc = f" — {m.description}" if m.description else ""
                out.append(f"- {m.name}{desc}")
            return "\n".join(out)

        parts = [f"Module im {sem}. Semester:"]
        if pflicht:
            parts.append(f"\nPFLICHTMODULE (vorgeschrieben, {len(pflicht)}):\n" + _fmt(pflicht))
        if wahlpflicht:
            parts.append(f"\nWAHLPFLICHTMODULE (wählbar, {len(wahlpflicht)}):\n" + _fmt(wahlpflicht))
        if sonstige:
            parts.append("\nWeitere Module (ohne Pflicht/Wahlpflicht-Angabe):\n" + _fmt(sonstige))
        return "\n".join(parts)

    @tool
    async def list_all_modules() -> str:
        """Listet alle Module des Studiengangs mit ihrem Semester (sofern bekannt)."""
        try:
            modules = (await db.execute(
                select(CurriculumModule).order_by(CurriculumModule.semester, CurriculumModule.name)
            )).scalars().all()
        except Exception:
            modules = []
        if not modules:
            return "Kein Modulhandbuch hinterlegt — bitte im Profil hochladen."
        lines = []
        for m in modules:
            sem = f"{m.semester}. Sem." if m.semester else "ohne Semester"
            typ = f", {m.module_type}" if m.module_type else ""
            lines.append(f"- [{sem}{typ}] {m.name}")
        return "Alle Module im Modulhandbuch:\n" + "\n".join(lines)

    @tool
    async def module_details(module_name: str) -> str:
        """Gibt Details zu EINEM Modul zurück: Semester, Beschreibung, Vorgängermodule
        und vermittelte Kompetenzen.

        Args:
            module_name: Name (oder Teilname) des Moduls.
        """
        q = (module_name or "").strip().lower()
        if not q:
            return "Bitte einen Modulnamen angeben."
        try:
            modules = (await db.execute(select(CurriculumModule))).scalars().all()
        except Exception:
            modules = []
        if not modules:
            return "Kein Modulhandbuch hinterlegt — bitte im Profil hochladen."
        m = next((x for x in modules if x.name.lower() == q), None) \
            or next((x for x in modules if q in x.name.lower() or x.name.lower() in q), None)
        if m is None:
            return f"Kein Modul zu '{module_name}' im Modulhandbuch gefunden."
        parts = [f"Modul: {m.name}"]
        if m.module_type:
            parts.append(f"Art: {m.module_type}modul")
        if m.semester:
            parts.append(f"Semester: {m.semester}")
        if m.description:
            parts.append(f"Beschreibung: {m.description}")
        if m.prerequisites:
            parts.append("Vorgängermodule: " + ", ".join(m.prerequisites))
        if m.competencies:
            parts.append("Kompetenzen: " + ", ".join(m.competencies))
        return "\n".join(parts)

    llm = get_llm(temperature=0.2)
    return create_agent(
        model=llm,
        tools=[modules_by_semester, list_all_modules, module_details],
        prompt=_SYSTEM_PROMPT,
    )


async def run_curriculum_agent(message: str, db: AsyncSession) -> str:
    """Führt den CurriculumAgent aus und beantwortet Fragen zum Studienverlauf."""
    agent = create_curriculum_agent(db)
    try:
        result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
        return extract_text_output(result) or "Die Anfrage konnte nicht beantwortet werden."
    except Exception as exc:
        logger.error("CurriculumAgent fehlgeschlagen: %s", exc)
        return "Der Curriculum-Agent ist momentan nicht erreichbar. Bitte später erneut versuchen."
