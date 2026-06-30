"""TutorAgent — beantwortet Fragen aus Lernmaterial (RAG) und generiert Quizze.

Nutzt LangChain 1.x `create_agent` (LangGraph-basiert). Der Agent entscheidet
selbstständig, welche Dokumente er durchsucht, bevor er antwortet.
Für Quiz-Generierung wird `with_structured_output` eingesetzt.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from langgraph.prebuilt import create_react_agent as create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    ainvoke_with_model_fallback,
    extract_text_output,
    get_llm,
    run_agent_with_model_fallback,
    run_with_model_fallback,
)
from app.models.document import Document
from app.rag.retriever import has_indexed_source, retrieve_context

logger = logging.getLogger(__name__)

# ── System-Prompts ──────────────────────────────────────────────────────────

_AGENT_SYSTEM_PROMPT = """
Du bist ein intelligenter Tutor-Agent für Studierende an der HTW Berlin.

Deine Aufgaben:
- Fragen zu Lernmaterialien beantworten, wenn die Frage Dokumente, PDFs,
  hochgeladene Unterlagen, Moodle oder Kursmaterialien erwähnt
- Konzepte erklären, Zusammenhänge aufzeigen
- Den Lernfortschritt durch gezielte Rückfragen fördern

Verhalten:
- Bei allgemeinen Konzeptfragen (z.B. Programmierung, SQL, JavaScript, Theorie)
  antworte direkt aus deinem Wissen, ohne Dokumenten- oder Moodle-Tools.
- Suche in hochgeladenen Lernmaterialien nur, wenn der Studierende explizit nach
  Dokumenten, PDFs, hochgeladenen Unterlagen, Quellen, Kursmaterialien oder Moodle fragt.
- Moodle-Kurse und Moodle-Indexierung nutzt du nur bei expliziten Moodle-/Kursmaterial-Fragen
  oder wenn der Studierende ausdrücklich Moodle-Materialien indexieren will.
- Falls auch dann nichts gefunden wird, sage das ehrlich
- Antworte auf Deutsch, es sei denn, der Studierende schreibt Englisch
- Sei ermutigend und klar, nicht übermäßig akademisch
- Wenn du mehrere Dokumente findest, nutze sie alle
""".strip()

_DIRECT_TUTOR_SYSTEM_PROMPT = """
Du bist ein Tutor-Agent für Studierende. Beantworte allgemeine Fach- und
Programmierfragen direkt, klar und didaktisch. Nutze keine Dokumenten-, RAG-,
Moodle- oder Datenbank-Tools. Wenn die Frage explizit nach hochgeladenen
Dokumenten, PDFs, Moodle, Kursmaterialien, Noten oder Deadlines fragt, sage nicht
ausweichend, sondern diese Fälle werden außerhalb dieses direkten Pfads behandelt.
""".strip()

_MATERIAL_CONTEXT_KEYWORDS = (
    "moodle",
    "dokument",
    "dokumente",
    "document",
    "documents",
    "pdf",
    "datei",
    "dateien",
    "file",
    "files",
    "hochgeladen",
    "uploaded",
    "upload",
    "unterlage",
    "unterlagen",
    "lernmaterial",
    "lernmaterialien",
    "material",
    "materialien",
    "course material",
    "kursmaterial",
    "slides",
    "folie",
    "folien",
    "skript",
    "quelle",
    "quellen",
    "chapter",
    "kapitel",
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


_MOODLE_RAG_SYSTEM_PROMPT = """
Du bist ein Tutor-Agent und Study Assistant. Beantworte die Frage ausschließlich
anhand des bereitgestellten Moodle-Kontexts aus dem aktuell ausgewählten Kurs.
Vermische keine Materialien aus anderen Kursen. Wenn der Kontext nicht ausreicht,
sage das ehrlich.

Wenn ein Moodle-Dokument, eine Session oder Folien erklärt werden sollen, liefere
eine ausführliche, lernorientierte Antwort mit diesen Teilen, soweit der Kontext
sie hergibt:
- Kurze Zusammenfassung
- Hauptthemen
- Wichtige Konzepte und Begriffe
- Beispiele aus dem Material, falls vorhanden
- Lernziele
- Key Takeaways
- 3 bis 5 optionale Quizfragen zur Selbstkontrolle

Schreibe didaktisch, konkret und hilfreich. Antworte in der Sprache der Frage;
bei deutschen Prompts auf Deutsch.
""".strip()


def _needs_material_context(message: str) -> bool:
    text = (message or "").lower()
    return any(keyword in text for keyword in _MATERIAL_CONTEXT_KEYWORDS)


def _normalize_course_id(course_id):
    if isinstance(course_id, str) and course_id.isdigit():
        return int(course_id)
    return course_id


def _iter_moodle_context_sections(moodle_context: dict | None):
    if not isinstance(moodle_context, dict):
        return
    for section in moodle_context.get("sections") or []:
        if isinstance(section, dict):
            yield section


def _is_selected_moodle_material_request(message: str, moodle_context: dict | None) -> bool:
    if not isinstance(moodle_context, dict) or not moodle_context.get("course_id"):
        return False
    text = (message or "").lower()
    if not text:
        return False
    if any(keyword in text for keyword in _SELECTED_MOODLE_MATERIAL_KEYWORDS):
        return True
    for section in _iter_moodle_context_sections(moodle_context):
        section_name = str(section.get("section_name") or "").lower()
        if section_name and section_name in text:
            return True
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            for key in ("name", "filename"):
                label = str(item.get(key) or "").lower()
                if label and label in text:
                    return True
    return False


def _matching_moodle_sources(message: str, moodle_context: dict | None) -> list[str] | None:
    matched_sources = [f["filename"] for f in _matching_moodle_files(message, moodle_context)]
    if not matched_sources:
        return None
    return list(dict.fromkeys(matched_sources))


def _is_supported_moodle_file(filename: str) -> bool:
    return filename.lower().endswith((".pdf", ".pptx", ".docx"))


def _matching_moodle_files(message: str, moodle_context: dict | None) -> list[dict]:
    text = (message or "").lower()
    matched: list[dict] = []
    for section in _iter_moodle_context_sections(moodle_context):
        section_name = str(section.get("section_name") or "")
        section_matches = bool(section_name and section_name.lower() in text)
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename") or "").strip()
            if not filename or not _is_supported_moodle_file(filename):
                continue
            name = str(item.get("name") or "").strip()
            item_matches = any(
                label and label.lower() in text
                for label in (filename, name)
            )
            if section_matches or item_matches:
                matched.append({
                    "filename": filename,
                    "fileurl": item.get("fileurl") or item.get("url") or "",
                    "module": name,
                    "section": section_name,
                })
    by_filename: dict[str, dict] = {}
    for file_info in matched:
        by_filename[file_info["filename"]] = file_info
    return list(by_filename.values())


async def _load_matching_moodle_files_from_service(
    message: str,
    moodle_context: dict,
) -> list[dict]:
    from app.services import moodle_service

    course_id = moodle_context.get("course_id")
    if not course_id or not moodle_service.is_configured():
        return []
    try:
        files = await moodle_service.get_course_files(int(course_id) if str(course_id).isdigit() else course_id)
    except Exception as exc:
        logger.warning("Moodle-Dateiliste konnte nicht geladen werden: %s", exc)
        return []

    text = (message or "").lower()
    matched: list[dict] = []
    for file_info in files:
        filename = str(file_info.get("filename") or "")
        section = str(file_info.get("section") or "")
        module = str(file_info.get("module") or "")
        if not filename or not _is_supported_moodle_file(filename):
            continue
        if (
            filename.lower() in text
            or (section and section.lower() in text)
            or (module and module.lower() in text)
        ):
            matched.append(file_info)
    by_filename: dict[str, dict] = {}
    for file_info in matched:
        by_filename[file_info["filename"]] = file_info
    return list(by_filename.values())


def _selected_moodle_course_label(moodle_context: dict | None) -> str:
    if not isinstance(moodle_context, dict):
        return "dem ausgewählten Moodle-Kurs"
    return str(
        moodle_context.get("course_name")
        or moodle_context.get("course_shortname")
        or "dem ausgewählten Moodle-Kurs"
    )


def _llm_response_to_text(response) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return ""


async def _ensure_moodle_files_indexed(
    files: list[dict],
    moodle_context: dict,
    chat_id: str | None,
    user_id: str,
    metadata_filter: dict,
) -> tuple[int, int]:
    from app.rag.pipeline import index_text
    from app.services import moodle_service

    course_name = _selected_moodle_course_label(moodle_context)
    indexed_files = 0
    chunks = 0
    for file_info in files:
        filename = str(file_info.get("filename") or "").strip()
        fileurl = str(file_info.get("fileurl") or "").strip()
        if not filename or not fileurl:
            continue
        if has_indexed_source(filename, user_id=user_id, metadata_filter=metadata_filter):
            continue
        try:
            text = await moodle_service.download_file_text(fileurl, filename)
        except moodle_service.MoodleError as exc:
            logger.warning("Moodle-Datei konnte nicht geladen werden (%s): %s", filename, exc)
            continue
        if not text:
            continue
        n_chunks = await asyncio.to_thread(
            index_text,
            filename,
            text,
            chat_id,
            user_id,
            {
                **metadata_filter,
                "course_name": course_name,
                "section": file_info.get("section") or "",
                "module": file_info.get("module") or "",
            },
        )
        if n_chunks:
            indexed_files += 1
            chunks += n_chunks
    return indexed_files, chunks


async def _answer_from_selected_moodle_material(
    message: str,
    chat_id: str | None,
    user_id: str,
    moodle_context: dict,
) -> str:
    course_id = _normalize_course_id(moodle_context.get("course_id"))
    course_label = _selected_moodle_course_label(moodle_context)
    matched_files = _matching_moodle_files(message, moodle_context)
    if not matched_files or any(not f.get("fileurl") for f in matched_files):
        service_files = await _load_matching_moodle_files_from_service(message, moodle_context)
        by_filename = {f["filename"]: f for f in service_files if f.get("filename")}
        for file_info in matched_files:
            if file_info.get("filename") in by_filename:
                merged = {**file_info, **by_filename[file_info["filename"]]}
                by_filename[file_info["filename"]] = merged
            else:
                by_filename[file_info["filename"]] = file_info
        matched_files = list(by_filename.values())
    source_filter = [f["filename"] for f in matched_files] or _matching_moodle_sources(message, moodle_context)
    metadata_filter = {"moodle": "1", "course_id": course_id}

    context = await retrieve_context(
        message,
        source_filter=source_filter,
        n_results=12,
        threshold=None,
        chat_id=None,
        user_id=user_id,
        metadata_filter=metadata_filter,
    )
    if not context and matched_files:
        await _ensure_moodle_files_indexed(
            matched_files, moodle_context, chat_id, user_id, metadata_filter
        )
        context = await retrieve_context(
            message,
            source_filter=source_filter,
            n_results=12,
            threshold=None,
            chat_id=None,
            user_id=user_id,
            metadata_filter=metadata_filter,
        )
    if not context and source_filter:
        context = await retrieve_context(
            message,
            n_results=12,
            threshold=None,
            chat_id=None,
            user_id=user_id,
            metadata_filter=metadata_filter,
        )
    if not context:
        return (
            f"Ich habe fuer {course_label} noch keine passenden indexierten Moodle-Inhalte "
            "gefunden oder konnte die passende Moodle-Datei nicht lesen. Unterstuetzt "
            "werden PDF, PPTX und DOCX."
        )

    source_note = f"\n\nAngefragte Datei(en): {', '.join(source_filter)}" if source_filter else ""
    try:
        response = await ainvoke_with_model_fallback([
            SystemMessage(content=_MOODLE_RAG_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Aktuell ausgewaehlter Moodle-Kurs: {course_label} "
                    f"(Course ID: {course_id}).{source_note}\n\n"
                    f"Frage: {message}\n\n"
                    f"Moodle-Kontext:\n{context}"
                )
            ),
        ], temperature=0.2)
        text = response.content if isinstance(response.content, str) else ""
        if isinstance(response.content, list):
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in response.content
            )
        return text.strip() or "Ich konnte leider keine Antwort generieren."
    except Exception as exc:
        logger.error("TutorAgent Moodle-RAG-Antwort fehlgeschlagen: %s", exc)
        return "Der Tutor ist momentan nicht erreichbar. Bitte spaeter erneut versuchen."

_QUIZ_SYSTEM_PROMPT = """
Du bist ein Tutor-Agent der Multiple-Choice- und Wahr/Falsch-Fragen generiert.

Regeln:
- Ausschließlich Fragen, die direkt aus dem bereitgestellten Kontext ableitbar sind
- Alle Fragen und Antworten auf Deutsch
- Multiple-Choice: genau 4 Optionen (A–D), genau eine korrekt
- Wahr/Falsch: keine Optionen, Antwort ist "true" oder "false"
- ca. 70 % Multiple Choice, 30 % Wahr/Falsch
- Variiere den Schwierigkeitsgrad
- KEINE Fragen zu organisatorischen Themen wie Deadlines, Abgabedaten, Prüfungsmodalitäten, Benotungsschemas, Anwesenheitspflicht, Semesterplanung oder Kursorganisation — nur inhaltliche Fachfragen
""".strip()


# ── Pydantic-Schema für Quiz Structured Output ────────────────────────────────

_QUIZ_JSON_INSTRUCTIONS = """
Antworte ausschliesslich mit einem validen JSON-Objekt ohne Markdown.
Das JSON muss diese Form haben:
{
  "title": "Kurzer Quiztitel",
  "questions": [
    {
      "type": "MC" oder "TF",
      "question": "Fragetext",
      "options": ["Aussage A", "Aussage B", "Aussage C", "Aussage D"] fuer MC, sonst null,
      "correct_answer": "A" | "B" | "C" | "D" fuer MC oder "true" | "false" fuer TF,
      "explanation": "Kurze Begruendung aus dem Material"
    }
  ]
}
Jede Frage braucht explanation. Bei Multiple Choice muss correct_answer der Buchstabe
der richtigen Option sein, nicht der Optionstext.
""".strip()


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

def _extract_json_object(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text or ""):
        try:
            value, _end = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "questions" in value:
            return value
    return None


def _normalize_quiz_question(raw: dict) -> dict:
    q = dict(raw)
    q["type"] = str(q.get("type", "")).upper()
    if not str(q.get("explanation", "")).strip():
        q["explanation"] = "Die Antwort ergibt sich aus dem bereitgestellten Lernmaterial."

    if q["type"] == "MC":
        options = q.get("options")
        if isinstance(options, list):
            q["options"] = [str(option) for option in options[:4]]
            answer = str(q.get("correct_answer", "")).strip()
            if answer.upper() in ("A", "B", "C", "D"):
                q["correct_answer"] = answer.upper()
            else:
                answer_norm = answer.casefold()
                for idx, option in enumerate(q["options"]):
                    if str(option).strip().casefold() == answer_norm:
                        q["correct_answer"] = "ABCD"[idx]
                        break
        return q

    if q["type"] == "TF":
        q["correct_answer"] = str(q.get("correct_answer", "")).strip().lower()
        q["options"] = None
    return q


def _quiz_payload_from_json_text(text: str) -> dict | None:
    payload = _extract_json_object(text)
    if not payload:
        return None
    questions = []
    for raw_question in payload.get("questions") or []:
        if not isinstance(raw_question, dict):
            continue
        question = _normalize_quiz_question(raw_question)
        if _is_valid_quiz_question(question):
            questions.append(question)
    if not questions:
        return None
    return {
        "title": str(payload.get("title") or "Quiz").strip() or "Quiz",
        "questions": questions,
    }


def create_tutor_agent(db: AsyncSession, chat_id: str | None = None, user_id: str = "local", llm=None):
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

    llm = llm or get_llm(temperature=0.0)
    return create_agent(
        model=llm,
        tools=[
            search_learning_material,
            search_in_document,
            list_available_documents,
            list_moodle_courses,
            index_moodle_course,
        ],
        prompt=_AGENT_SYSTEM_PROMPT,
    )


# ── Öffentliche API ───────────────────────────────────────────────────────────

async def run_tutor_agent(
    message: str,
    db: AsyncSession,
    chat_id: str | None = None,
    user_id: str = "local",
    moodle_context: dict | None = None,
) -> str:
    """Führt den TutorAgent für eine Konversationsrunde aus."""
    if _is_selected_moodle_material_request(message, moodle_context):
        return await _answer_from_selected_moodle_material(
            message, chat_id, user_id, moodle_context or {}
        )

    if not _needs_material_context(message):
        try:
            response = await ainvoke_with_model_fallback([
                SystemMessage(content=_DIRECT_TUTOR_SYSTEM_PROMPT),
                HumanMessage(content=message),
            ], temperature=0.2)
            text = _llm_response_to_text(response)
            return text.strip() or "Ich konnte leider keine Antwort generieren."
        except Exception as exc:
            logger.error("TutorAgent Direktantwort fehlgeschlagen: %s", exc)
            return "Der Tutor ist momentan nicht erreichbar. Bitte später erneut versuchen."

    try:
        result = await run_agent_with_model_fallback(
            lambda llm: create_tutor_agent(db, chat_id, user_id, llm=llm),
            {"messages": [HumanMessage(content=message)]},
            temperature=0.0,
        )
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
            async def _invoke(llm):
                structured_llm = llm.with_structured_output(_QuizSchema)
                return await structured_llm.ainvoke([
                    SystemMessage(content=_QUIZ_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ])

            result: _QuizSchema = await run_with_model_fallback(_invoke, temperature=0.3)
            quiz_payload = result.model_dump()
        except Exception as exc:
            quiz_payload = _quiz_payload_from_json_text(str(exc))
            if quiz_payload is None:
                try:
                    async def _invoke_json(llm):
                        return await llm.ainvoke([
                            SystemMessage(content=f"{_QUIZ_SYSTEM_PROMPT}\n\n{_QUIZ_JSON_INSTRUCTIONS}"),
                            HumanMessage(content=user_prompt),
                        ])

                    response = await run_with_model_fallback(_invoke_json, temperature=0.3)
                    quiz_payload = _quiz_payload_from_json_text(_llm_response_to_text(response))
                except Exception as json_exc:
                    logger.error("Quiz-Generierung JSON-Fallback (Runde %d) fehlgeschlagen: %s", round_idx + 1, json_exc)
                    quiz_payload = None
            if quiz_payload is None:
                logger.error("Quiz-Generierung (Runde %d) fehlgeschlagen: %s", round_idx + 1, exc)
                if valid:
                    break  # mit dem Bisherigen weitermachen
                raise RuntimeError("Quiz-Generierung fehlgeschlagen. Bitte spaeter erneut versuchen.")
            logger.warning("Quiz structured output failed; using parsed JSON fallback")

        title = title or quiz_payload.get("title")
        for q in quiz_payload.get("questions", []):
            qd = q.model_dump() if hasattr(q, "model_dump") else dict(q)
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


_REVIEW_SYSTEM_PROMPT = """
Du bist ein geduldiger Tutor und gehst mit dem/der Studierenden das Quiz-Ergebnis durch.
Konzentriere dich auf die FALSCH beantworteten Fragen und erkläre verständlich.

Struktur deiner Antwort (Markdown, auf Deutsch):
1. Eine kurze, motivierende Einordnung des Ergebnisses (1–2 Sätze).
2. Abschnitt "## Das solltest du dir nochmal ansehen": Gehe JEDE falsche Frage einzeln durch:
   - nenne die Frage,
   - die richtige Antwort,
   - WARUM sie richtig ist (nutze den bereitgestellten Lernmaterial-Kontext, wenn vorhanden),
   - das dahinterliegende Konzept in 1–2 Sätzen.
3. Abschnitt "## Empfehlung zum Wiederholen": Verweise konkret auf das/die Quelldokument(e)
   und nenne die 2–3 wichtigsten Themen, die der/die Studierende dort nachlesen sollte.

Erfinde keine Fakten. Wenn der Kontext nichts hergibt, erkläre auf Basis der Frage und der
hinterlegten Erklärung. Sei konkret und knapp — keine Floskeln.
""".strip()


async def generate_quiz_review(
    quiz_title: str,
    source_documents: list[str],
    course_name: str | None,
    score: int,
    total: int,
    wrong_items: list[dict[str, Any]],
    user_id: str = "local",
) -> str:
    """Erstellt eine ausführliche, grounded Nachbesprechung eines Quiz-Versuchs.

    Holt passenden Lernmaterial-Kontext zu den falschen Fragen aus den Quelldokumenten
    und lässt das LLM die Ergebnisse Schritt für Schritt durchgehen.
    """
    percentage = round(score / total * 100, 1) if total else 0.0
    doc_label = course_name or ", ".join(source_documents) or "den Lernunterlagen"

    # Kontext zu den falsch beantworteten Fragen aus den Quelldokumenten ziehen
    context = ""
    if wrong_items and source_documents:
        query = " ".join((w.get("question") or "") for w in wrong_items)[:1500]
        try:
            context = await retrieve_context(
                query or "Hauptthemen und Konzepte",
                source_filter=source_documents,
                n_results=12,
                threshold=None,
                chat_id=None,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("Review-Kontext konnte nicht geladen werden: %s", exc)

    wrong_block_lines = []
    for i, w in enumerate(wrong_items, 1):
        wrong_block_lines.append(
            f"{i}. Frage: {w.get('question', '')}\n"
            f"   Deine Antwort: {w.get('given', '')}\n"
            f"   Richtige Antwort: {w.get('correct', '')}\n"
            f"   Hinterlegte Erklärung: {w.get('explanation') or '—'}"
        )
    wrong_block = "\n".join(wrong_block_lines) or "(keine falschen Fragen)"

    user_prompt = (
        f"Quiz: {quiz_title}\nModul/Material: {doc_label}\n"
        f"Ergebnis: {score}/{total} ({percentage}%)\n\n"
        f"Falsch beantwortete Fragen:\n{wrong_block}\n\n"
    )
    if context:
        user_prompt += f"Auszug aus dem Lernmaterial (zur Begründung nutzen):\n{context[:6000]}"
    else:
        user_prompt += "(Kein Lernmaterial-Kontext verfügbar — erkläre auf Basis der Fragen.)"

    try:
        resp = await ainvoke_with_model_fallback([
            SystemMessage(content=_REVIEW_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ], temperature=0.3)
        text = (
            resp.content if isinstance(resp.content, str)
            else " ".join(p.get("text", "") for p in resp.content if isinstance(p, dict))
        )
        return text.strip() or "Die Nachbesprechung konnte nicht erstellt werden."
    except Exception as exc:
        logger.error("Quiz-Nachbesprechung fehlgeschlagen: %s", exc)
        raise RuntimeError("Die Nachbesprechung konnte nicht erstellt werden.")
