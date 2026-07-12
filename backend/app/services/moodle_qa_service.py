"""Moodle-QA — inhaltliche Fragen aus Moodle-Materialien beantworten OHNE Upload.

Ablauf:
1. Passenden belegten Moodle-Kurs zur Frage erkennen (LLM über die Kursliste).
2. Das Kursmaterial einmalig on-demand in die RAG-DB indizieren (danach gecached).
3. Relevanten Kontext (kursgefiltert) holen und die Frage beantworten.

Dieser Service macht den Chat unabhängig von manuellen Uploads: der/die Studierende
fragt einfach etwas, und die App findet selbst das richtige Modul in Moodle.
"""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import ainvoke_with_model_fallback
from app.observability import trace_bus
from app.rag.retriever import (
    count_indexed_chunks,
    has_indexed_course,
    relevant_sources_for_query,
    retrieve_context,
)
from app.services import moodle_service

logger = logging.getLogger(__name__)


_QUIZ_STOPWORDS = (
    "quiz", "kannst", "du", "bitte", "mir", "jetzt", "ein", "eine", "einen", "mit", "zu",
    "für", "fuer", "das", "den", "die", "der", "über", "ueber", "thema", "themen",
    "modul", "kurs", "frage", "fragen", "inhalt", "inhalte", "stoff",
    "erstell", "erstelle", "erstellen", "generier", "generiere", "generieren",
    "mach", "mache", "erzeug", "erzeuge", "gib", "starte", "create", "make", "about",
    "vollständig", "vollstaendig", "komplett", "gesamten", "gesamte", "umfassend",
    "ausführlich", "ausfuehrlich", "abdeckt", "abdecken", "abdeckende",
)


def _filter_files_by_keyword(all_names: list[str], topic: str) -> list[str]:
    """Wenn ein THEMENWORT direkt in einem Dateinamen vorkommt (z.B. „Virtualisierung"
    → …_02_Virtualisierung.pdf), liefere genau diese Datei(en). So bekommt ein
    Themen-Quiz nur die passende PDF statt semantisch verwandter Nachbarn.
    """
    words = [w.lower() for w in re.split(r"[\s()/,]+", topic or "") if len(w) >= 4]
    if not words:
        return []
    hits: list[str] = []
    for name in all_names:
        nl = name.lower()
        if any(w in nl for w in words) and name not in hits:
            hits.append(name)
    return hits


def _quiz_topic_query(message: str, course_name: str) -> str:
    """Extrahiert aus der Quiz-Anfrage den THEMEN-Teil (ohne Kursname/Quiz-Floskeln),
    damit die Relevanzsuche das richtige Material findet.
    """
    text = message or ""
    # Kurs-Namensbestandteile entfernen, damit das Thema dominiert
    for token in re.split(r"[\s\-/()]+", course_name or ""):
        if len(token) >= 4:
            text = re.sub(re.escape(token), " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\d+", " ", text)
    words = [w for w in re.split(r"[\s()/,]+", text) if w and w.lower() not in _QUIZ_STOPWORDS]
    cleaned = " ".join(words).strip()
    return cleaned or (message or "")


def _filter_files_by_section(files: list[dict], message: str) -> list[str]:
    """Wenn die Anfrage eine Woche/einen Abschnitt nennt (z.B. „Woche 3"), liefere
    nur die dazu passenden Dateien (Match über Dateiname ODER Moodle-Abschnitt).
    Sonst leere Liste. So wird ein „Woche 3"-Quiz nur aus Woche-3-Material gebaut.
    """
    text = (message or "").lower()
    m = re.search(
        r"\b(woche|week|kw|kapitel|einheit|lektion|session|thema|tag)\s*0*(\d{1,2})\b",
        text,
    )
    if not m:
        return []
    num = m.group(2)
    # Datei-/Abschnitts-Treffer: Wochen-Wort + optionaler Trenner + Zahl (mit Wortgrenze,
    # damit „3" nicht „13"/„30" trifft).
    pat = re.compile(rf"(?:woche|week|kw|kapitel|session|einheit)[\s_\-]*0*{num}\b", re.IGNORECASE)
    hits: list[str] = []
    for f in files:
        haystack = f"{f.get('filename', '')} {f.get('section', '')} {f.get('module', '')}"
        name = f.get("filename")
        if name and pat.search(haystack) and name not in hits:
            hits.append(name)
    return hits


def _content(resp) -> str:
    c = getattr(resp, "content", resp)
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return str(c)


_COURSE_NAME_HINTS = (
    "verteilte anwendungen", "unternehmenssoftware", "produktionswirtschaft", "logistik",
    "informationssicherheit", "rechnernetze", "webtechnologien", "datenbank",
    "programmierung", "controlling", "statistik", "mathematik", "marketing",
    "software", "wirtschaftsrecht", "projektmanagement", "englisch",
)


async def _pick_course_for_question(question: str, courses: list[dict]) -> dict | None:
    """Bestimmt den passenden Kurs. Nennt die Frage ein Modul explizit → per Keyword
    (spart einen LLM-Call). Sonst entscheidet das LLM.
    """
    if not courses:
        return None

    # 1) Günstiger Keyword-Weg: nennt die Frage einen Modul-/Kursnamen direkt?
    q = (question or "").lower()
    if any(h in q for h in _COURSE_NAME_HINTS):
        match = moodle_service._match_course(courses, question)
        if match is not None:
            return match

    # 2) Sonst LLM entscheiden lassen.
    listing = "\n".join(
        f"- {c.get('fullname') or c.get('shortname')}"
        for c in courses
        if c.get("fullname") or c.get("shortname")
    )
    prompt = (
        "Hier sind die aktuell belegten Moodle-Kurse eines Studierenden:\n"
        f"{listing}\n\n"
        "Zu welchem EINEN Kurs passt die folgende inhaltliche Frage am besten?\n"
        f"Frage: {question}\n\n"
        "Antworte AUSSCHLIESSLICH mit dem exakten Kursnamen aus der Liste oder mit 'KEINS', "
        "falls die Frage zu keinem Kurs passt."
    )
    try:
        resp = await ainvoke_with_model_fallback(
            [
                SystemMessage(content="Du ordnest Studienfragen dem passenden Modul zu."),
                HumanMessage(content=prompt),
            ],
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("Moodle-Kurswahl per LLM fehlgeschlagen: %s", exc)
        return None

    answer = _content(resp).strip().strip(".\"'")
    if not answer or "keins" in answer.lower():
        return None
    return moodle_service._match_course(courses, answer)


_ANSWER_SYSTEM = (
    "Du bist ein Tutor. Beantworte die Frage NUR anhand des bereitgestellten "
    "Moodle-Kursmaterials. Wenn das Material die Antwort nicht hergibt, sage das ehrlich. "
    "Antworte auf Deutsch, klar und strukturiert."
)


@trace_bus.traced_agent("moodle", "Moodle-QA")
async def answer_from_moodle(
    question: str,
    chat_id: str | None = None,
    user_id: str = "local",
) -> str:
    """Beantwortet eine inhaltliche Frage aus dem passenden Moodle-Kursmaterial."""
    if not moodle_service.is_configured():
        return (
            "Moodle ist nicht verbunden (kein MOODLE_TOKEN konfiguriert). "
            "Lade alternativ ein Dokument hoch, dann kann ich deine Frage beantworten."
        )

    trace_bus.publish("moodle", "moodle", "Moodle-Kurse laden", question[:120], status="start")
    try:
        courses = await moodle_service.get_moodle_courses()
    except moodle_service.MoodleError as exc:
        trace_bus.publish("moodle", "moodle", "Moodle-Fehler", str(exc), status="error")
        return f"Moodle-Kurse konnten nicht geladen werden: {exc}"

    course = await _pick_course_for_question(question, courses)
    if course is None:
        trace_bus.publish("moodle", "moodle", "Kein Modul erkannt", "", status="warn")
        return (
            "Ich konnte deiner Frage kein Moodle-Modul eindeutig zuordnen. "
            "Nenne bitte kurz das Modul (z. B. »… in Webtechnologien«)."
        )

    course_id = course.get("id")
    course_name = course.get("fullname") or course.get("shortname") or "Moodle-Kurs"
    trace_bus.publish("moodle", "moodle", f"Modul erkannt: {course_name}", f"course_id={course_id}", status="ok")

    # Material nur einmal indizieren (danach gecached).
    if not has_indexed_course(course_id):
        trace_bus.publish("moodle", "moodle", "Material wird indiziert", course_name, status="start")
        try:
            result = await moodle_service.index_course_by_name(course_name, chat_id=None, user_id=user_id)
            trace_bus.publish(
                "moodle", "moodle", "Material indiziert",
                f"{result.get('files_indexed', 0)} Datei(en), {result.get('chunks', 0)} Chunks",
                status="ok",
            )
        except moodle_service.MoodleError as exc:
            trace_bus.publish("moodle", "moodle", "Indizierung fehlgeschlagen", str(exc), status="error")
            return f"Das Material für {course_name} konnte nicht geladen werden: {exc}"
    else:
        trace_bus.publish("moodle", "moodle", "Material bereits indiziert", course_name, status="ok")

    # Kursgefilterten Kontext holen.
    context = await retrieve_context(
        question,
        n_results=12,
        threshold=None,
        chat_id=None,
        user_id=None,
        metadata_filter={"course_id": course_id},
    )
    trace_bus.publish("rag", "rag", "RAG-Suche (Moodle)", f"{len(context)} Zeichen Kontext", status="ok")
    if not context:
        return (
            f"Ich habe das Material für {course_name} gefunden, aber dazu keinen passenden "
            "Inhalt zu deiner Frage. Formuliere die Frage evtl. etwas anders."
        )

    prompt = (
        f"Modul: {course_name}\n\nFrage: {question}\n\n"
        f"Auszug aus dem Moodle-Kursmaterial:\n{context[:7000]}"
    )
    try:
        resp = await ainvoke_with_model_fallback(
            [SystemMessage(content=_ANSWER_SYSTEM), HumanMessage(content=prompt)],
            temperature=0.2,
        )
    except Exception as exc:
        logger.error("Moodle-Antwort fehlgeschlagen: %s", exc)
        return "Ich konnte gerade keine Antwort aus dem Moodle-Material erzeugen. Bitte später erneut."

    answer = _content(resp).strip()
    return answer + f"\n\n_(Quelle: Moodle-Kurs »{course_name}«)_"


_WEAKNESS_MARKERS = (
    "schwäch", "schwaech", "wissenslück", "wissensluec", "schwachstell", "lücken", "luecken",
    "weak", "die du findest", "wo ich schlecht", "meine fehler", "wo ich schwach",
)


def _is_weakness_quiz(topic: str) -> bool:
    return any(m in (topic or "").lower() for m in _WEAKNESS_MARKERS)


async def _pick_weakest_current_semester_course(courses: list[dict], db):
    """Wählt anhand des Quiz-Profils das schwächste Modul des AKTUELLEN Semesters und
    liefert den passenden Moodle-Kurs. Returns (course | None, hinweis)."""
    from app.api.v1.tutor import _compute_topic_mastery
    from app.core.config import settings
    from app.services.moodle_context_service import _detect_course_semester

    try:
        topics = await _compute_topic_mastery(db)
    except Exception:
        topics = []
    weak = sorted([t for t in topics if t.get("score", 100) < 80], key=lambda t: t.get("score", 100))
    if not weak:
        return None, "Ich habe in deinem Profil noch keine Schwächen gefunden — mach zuerst ein paar Quizze im Quiz-Tab."

    cur = settings.current_semester
    for t in weak:
        course = moodle_service._match_course(courses, t.get("topic", ""))
        if course is not None and _detect_course_semester(course) == cur:
            trace_bus.publish(
                "moodle", "moodle", f"Schwächstes Modul (Sem. {cur}): {t.get('topic')}",
                f"{t.get('score')}%", status="ok",
            )
            return course, ""
    return None, (
        f"Deine erkannten Schwächen liegen aktuell nicht in Modulen des {cur}. Semesters "
        "(oder ich konnte sie keinem Moodle-Kurs zuordnen). Nenne mir sonst kurz das Modul."
    )


async def create_quiz_from_moodle(
    topic: str,
    num_questions: int,
    db,
    user_id: str = "local",
):
    """Erstellt ein ECHTES, gespeichertes Quiz aus dem Moodle-Material des passenden Moduls.

    Returns (quiz | None, nachricht). Bei Erfolg ist ``quiz`` das persistierte Quiz-Objekt.
    """
    from app.services.tutor_service import generate_quiz

    if not moodle_service.is_configured():
        return None, "Moodle ist nicht verbunden (kein MOODLE_TOKEN). Ich kann daraus kein Quiz erstellen."

    trace_bus.publish("moodle", "moodle", "Modul für Quiz ermitteln", topic[:120], status="start")
    try:
        courses = await moodle_service.get_moodle_courses()
    except moodle_service.MoodleError as exc:
        return None, f"Moodle-Kurse konnten nicht geladen werden: {exc}"

    # „Quiz für meine Schwächen" → schwächstes Modul des AKTUELLEN Semesters automatisch
    # aus dem Profil wählen (statt nach einem Modul zu fragen).
    if _is_weakness_quiz(topic):
        course, hint = await _pick_weakest_current_semester_course(courses, db)
        if course is None:
            return None, hint
    else:
        course = await _pick_course_for_question(topic, courses)
        if course is None:
            return None, (
                "Zu welchem Modul soll ich das Quiz erstellen? Nenne bitte kurz das Modul "
                "(z. B. »Quiz zu Verteilte Anwendungen«)."
            )

    course_id = course.get("id")
    course_name = course.get("fullname") or course.get("shortname") or "Moodle-Kurs"
    trace_bus.publish("moodle", "moodle", f"Modul erkannt: {course_name}", f"course_id={course_id}", status="ok")

    if not has_indexed_course(course_id):
        trace_bus.publish("moodle", "moodle", "Material wird indiziert", course_name, status="start")
        try:
            await moodle_service.index_course_by_name(course_name, chat_id=None, user_id=user_id)
        except moodle_service.MoodleError as exc:
            return None, f"Das Material für {course_name} konnte nicht geladen werden: {exc}"

    # Kurs-Dateien holen (für Wochen-/Abschnittsfilter und Fallback).
    try:
        files = await moodle_service.get_course_files(course_id)
    except moodle_service.MoodleError:
        files = []
    all_names = [f["filename"] for f in files if f.get("filename")]

    # Schwächen-Quiz → ganzes Modul abfragen (der verrauschte Anfragetext taugt nicht als Thema).
    section_files = [] if _is_weakness_quiz(topic) else _filter_files_by_section(files, topic)
    topic_query = "" if _is_weakness_quiz(topic) else _quiz_topic_query(topic, course_name)
    keyword_files = _filter_files_by_keyword(all_names, topic_query) if topic_query else []
    if section_files:
        filenames = section_files
        trace_bus.publish("rag", "rag", "Woche/Abschnitt gewählt", ", ".join(filenames)[:200], status="ok")
    elif keyword_files:
        # 2) Themenwort steht direkt im Dateinamen (z.B. „Virtualisierung") → nur diese Datei(en).
        filenames = keyword_files
        trace_bus.publish("rag", "rag", "Thema im Dateinamen gefunden", ", ".join(filenames)[:200], status="ok")
    else:
        # 3) Sonst semantisch die zum THEMA relevanten Dateien wählen (nicht ganzer Kurs).
        relevant = relevant_sources_for_query(topic_query, metadata_filter={"course_id": course_id}) if topic_query else []
        if relevant:
            filenames = relevant
            trace_bus.publish("rag", "rag", "Relevantes Material gewählt", ", ".join(filenames)[:200], status="ok")
        else:
            filenames = all_names  # 4) Fallback: ganzer Kurs
    if not filenames:
        return None, f"Für {course_name} sind über Moodle keine indexierbaren Materialien verfügbar."

    # Keine Anzahl genannt (num_questions <= 0) → automatisch am Stoffumfang ausrichten:
    # ~0,8 Fragen pro indexiertem Abschnitt (Chunk), damit der Inhalt abgedeckt wird.
    if num_questions <= 0:
        chunks = count_indexed_chunks(source_documents=filenames)
        num_questions = max(5, min(20, round(chunks * 0.8))) if chunks else 8
        trace_bus.publish(
            "rag", "rag", f"Fragenanzahl automatisch: {num_questions}",
            f"aus {chunks} Abschnitten", status="ok",
        )

    # generate_quiz → generate_quiz_with_agent publiziert selbst die Tutor-Agent-Events.
    trace_bus.add_tool("Tutor-Agent (Quiz-Generierung)")
    try:
        quiz, _questions = await generate_quiz(
            source_documents=filenames,
            num_questions=num_questions,
            db=db,
            course_name=course_name,
            chat_id=None,
            user_id=user_id,
        )
    except (ValueError, RuntimeError) as exc:
        trace_bus.publish("error", "tutor", "Quiz-Generierung fehlgeschlagen", str(exc)[:120], status="error")
        return None, f"Ich konnte kein Quiz aus dem Material von {course_name} erstellen: {exc}"

    trace_bus.publish("tool", "tutor", "Quiz erstellt", f"{quiz.question_count} Fragen", status="ok")
    trace_bus.set_quiz({"id": quiz.id, "title": quiz.title, "question_count": quiz.question_count})
    return quiz, (
        f"Ich habe ein Quiz mit **{quiz.question_count} Fragen** zum Modul »{course_name}« erstellt "
        "— komplett aus dem Moodle-Material. Du kannst es unten öffnen und im Quiz-Tab starten."
    )
