"""Curriculum-Service — extrahiert aus einem Modulhandbuch eine strukturierte
Modul-Liste inkl. Vorgänger-Beziehungen (welches Modul baut auf welchem auf).

Das Modulhandbuch ist oft lang, daher wird der Text in Abschnitte zerlegt, pro
Abschnitt per LLM (Structured Output) extrahiert und anschließend nach Modulnamen
zusammengeführt. Das Ergebnis landet in der Tabelle ``curriculum_modules`` und wird
vom EvaluatorAgent genutzt, um bei Wissenslücken die Vorgängermodule zu empfehlen.
"""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import get_llm
from app.models.curriculum import CurriculumModule

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 12000
_CHUNK_OVERLAP = 800
_MAX_CHUNKS = 30  # Sicherheitsgrenze gegen riesige PDFs

_SYSTEM_PROMPT = """
Du extrahierst aus einem Modulhandbuch einer Hochschule die einzelnen MODULE.

Für jedes Modul, das im Textabschnitt beschrieben wird, gib zurück:
- name: der genaue Modulname
- description: 1–2 Sätze, worum es im Modul geht
- semester: empfohlenes Fachsemester, falls genannt (sonst null)
- prerequisites: Liste der MODULNAMEN, auf denen das Modul aufbaut bzw. die als
  Voraussetzung / empfohlene Vorkenntnisse genannt werden. Nutze die echten Modulnamen,
  keine vagen Formulierungen. Wenn keine genannt sind: leere Liste.
- competencies: 2–5 zentrale Kompetenzen/Themen, die das Modul vermittelt.

Regeln:
- Erfinde keine Module und keine Voraussetzungen, die nicht im Text stehen.
- Gib nur Module zurück, die in DIESEM Abschnitt tatsächlich beschrieben werden.
""".strip()


class _ModuleSchema(BaseModel):
    name: str
    description: str = ""
    semester: str | None = None
    module_type: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    competencies: list[str] = Field(default_factory=list)


class _ModulesSchema(BaseModel):
    modules: list[_ModuleSchema]


# Kopfblock einer Modulseite im HTW-Modulhandbuch, z.B.:
#   "... <Modulname> 2310\n 1 Studiengang zugeordnete: ...
#    SEMESTERZUORDNUNG5 ... STATUS DES MODULS Pflichtmodul ..."
# Diese strukturierten Felder sind VERBINDLICH und zuverlässiger als die LLM-Extraktion.
_BLOCK_SPLIT_RE = re.compile(r"(?=\n[^\n]{3,80} \d{3,4}\n 1 Studiengang zugeordnete)")
_NAME_RE = re.compile(r"\n([^\n]{3,80}) \d{3,4}\n 1 Studiengang zugeordnete")
_SEM_RE = re.compile(r"SEMESTERZUORDNUNG\s*(\d+)")
_STATUS_RE = re.compile(r"STATUS DES MODULS\s*(Pflicht|Wahlpflicht)modul", re.IGNORECASE)


def parse_module_headers(text: str) -> dict[str, dict]:
    """Liest aus dem Modulhandbuch-Text die strukturierten Kopfblöcke aus und liefert
    je Modulname (lowercase) {name, semester, module_type}. Deterministisch (Regex),
    daher genauer als die LLM-Extraktion für Semester & Pflicht/Wahlpflicht.
    """
    out: dict[str, dict] = {}
    for block in _BLOCK_SPLIT_RE.split(text or ""):
        nm = _NAME_RE.search(block)
        if not nm:
            continue
        name = nm.group(1).strip()
        sem_m = _SEM_RE.search(block)
        st_m = _STATUS_RE.search(block)
        # Semesterzuordnung 0 bedeutet "keinem festen Semester zugeordnet" → None
        semester = sem_m.group(1) if (sem_m and sem_m.group(1) != "0") else None
        module_type = None
        if st_m:
            module_type = "Pflicht" if st_m.group(1).lower() == "pflicht" else "Wahlpflicht"
        if semester or module_type:
            out[name.lower()] = {"name": name, "semester": semester, "module_type": module_type}
    return out


def _chunk(text: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n and len(chunks) < _MAX_CHUNKS:
        end = min(start + _CHUNK_SIZE, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = end - _CHUNK_OVERLAP
    return chunks


async def extract_and_store(text: str, db: AsyncSession) -> dict:
    """Extrahiert Module aus dem Modulhandbuch-Text und speichert sie (Replace).

    Returns Statistik-Dict {modules, with_prerequisites}.
    """
    if not text or not text.strip():
        return {"modules": 0, "with_prerequisites": 0}

    llm = get_llm(temperature=0.0)
    structured = llm.with_structured_output(_ModulesSchema)

    merged: dict[str, _ModuleSchema] = {}
    for chunk in _chunk(text):
        try:
            result: _ModulesSchema = await structured.ainvoke([
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content="Modulhandbuch-Abschnitt:\n\n" + chunk),
            ])
        except Exception as exc:
            logger.warning("Curriculum-Extraktion (Abschnitt) fehlgeschlagen: %s", exc)
            continue

        for m in result.modules:
            name = (m.name or "").strip()
            if not name:
                continue
            key = name.lower()
            if key not in merged:
                merged[key] = m
            else:
                # Felder zusammenführen
                cur = merged[key]
                if not cur.description and m.description:
                    cur.description = m.description
                if not cur.semester and m.semester:
                    cur.semester = m.semester
                cur.prerequisites = sorted({*cur.prerequisites, *m.prerequisites})
                cur.competencies = sorted({*cur.competencies, *m.competencies})

    # Verbindliche Felder (Semester + Pflicht/Wahlpflicht) aus den strukturierten
    # Kopfblöcken überlagern — deterministisch und damit genauer als die LLM-Werte.
    headers = parse_module_headers(text)
    for key, h in headers.items():
        if key in merged:
            merged[key].semester = h["semester"]
            merged[key].module_type = h["module_type"]
        else:
            merged[key] = _ModuleSchema(
                name=h["name"], semester=h["semester"], module_type=h["module_type"]
            )

    if not merged:
        return {"modules": 0, "with_prerequisites": 0}

    try:
        await db.execute(delete(CurriculumModule))
        for m in merged.values():
            db.add(CurriculumModule(
                name=m.name.strip(),
                description=(m.description or "").strip() or None,
                semester=(m.semester or None),
                module_type=(m.module_type or None),
                prerequisites=[p.strip() for p in m.prerequisites if p.strip()],
                competencies=[c.strip() for c in m.competencies if c.strip()],
            ))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Curriculum konnte nicht gespeichert werden: %s", exc)
        raise

    with_prereq = sum(1 for m in merged.values() if m.prerequisites)
    return {"modules": len(merged), "with_prerequisites": with_prereq}


async def suggest_module(documents: list[str], db: AsyncSession, user_id: str = "local") -> str | None:
    """Ermittelt anhand des Dokumentinhalts das am besten passende Modul aus dem
    Modulhandbuch. Gibt den Modulnamen zurück oder None.
    """
    from app.models.curriculum import CurriculumModule
    from app.rag.retriever import retrieve_context

    modules = (await db.execute(select(CurriculumModule).order_by(CurriculumModule.name))).scalars().all()
    if not modules:
        return None

    context = await retrieve_context(
        "Hauptthemen, Konzepte und Inhalte dieses Dokuments",
        source_filter=documents or None,
        n_results=6,
        threshold=None,
        chat_id=None,
        user_id=user_id,
    )
    if not context:
        return None

    module_names = [m.name for m in modules]
    name_list = "\n".join(f"- {n}" for n in module_names)
    prompt = (
        "Hier ist eine Liste der Module eines Studiengangs:\n" + name_list +
        "\n\nUnd hier ein Auszug aus einem Lerndokument:\n" + context[:4000] +
        "\n\nWelches EINE Modul aus der Liste passt thematisch am besten zu diesem Dokument? "
        "Antworte AUSSCHLIESSLICH mit dem exakten Modulnamen aus der Liste oder mit 'KEINS', "
        "falls keines passt."
    )

    llm = get_llm(temperature=0.0)
    try:
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        answer = (resp.content if isinstance(resp.content, str)
                  else " ".join(p.get("text", "") for p in resp.content if isinstance(p, dict))).strip()
    except Exception as exc:
        logger.warning("Modul-Vorschlag fehlgeschlagen: %s", exc)
        return None

    answer_l = answer.lower().strip().strip(".\"'")
    if not answer_l or "keins" in answer_l:
        return None
    # exakter / enthaltener Treffer
    for n in module_names:
        if n.lower() == answer_l:
            return n
    for n in module_names:
        if answer_l in n.lower() or n.lower() in answer_l:
            return n
    return None
