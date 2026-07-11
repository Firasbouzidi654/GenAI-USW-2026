"""In-Process Pub/Sub für Live-Trace-Events (Observability, nur Präsentation).

Die Agenten rufen :func:`publish` an Schlüsselstellen auf. Das Dashboard (eigener
Port, siehe :mod:`app.observability.dashboard`) abonniert via :func:`subscribe`.
Alles läuft im selben Prozess; ohne Abonnenten kostet publish praktisch nichts.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Aktuelle Trace-ID des laufenden Requests (pro Chat-Anfrage gesetzt).
current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)

# Provenance des laufenden Requests: welche Tools/Agents + welche Quell-Dokumente
# wurden zur Beantwortung genutzt. Ein veränderliches Dict, das Agents/RAG befüllen
# und der Prompt-Endpunkt am Ende an den Chat mitschickt.
current_provenance: ContextVar[dict | None] = ContextVar("current_provenance", default=None)

_subscribers: set[asyncio.Queue] = set()
_recent: list[dict] = []          # Ring-Puffer der letzten Events (Debug/HTTP)
_RECENT_MAX = 300
_seq = itertools.count(1)


def new_trace_id() -> str:
    return f"t{int(time.time() * 1000)}"


def set_trace_id(trace_id: str):
    """Setzt die aktuelle Trace-ID im ContextVar; gibt das Reset-Token zurück."""
    return current_trace_id.set(trace_id)


def start_provenance() -> dict:
    """Startet die Provenance-Sammlung für den aktuellen Request und gibt das Dict zurück."""
    prov: dict = {"tools": [], "sources": []}
    current_provenance.set(prov)
    return prov


def clear_provenance() -> None:
    current_provenance.set(None)


def add_tool(name: str) -> None:
    """Vermerkt ein genutztes Tool/Agent (z.B. 'Moodle-QA')."""
    prov = current_provenance.get()
    if prov is not None and name and name not in prov["tools"]:
        prov["tools"].append(name)


def add_source(name: str, kind: str = "", course: str | None = None) -> None:
    """Vermerkt eine genutzte Quelle (Dokument/Datei), optional mit Moodle-Kurs."""
    prov = current_provenance.get()
    if prov is None or not name:
        return
    for s in prov["sources"]:
        if s.get("name") == name and s.get("course") == course:
            return
    prov["sources"].append({"name": name, "kind": kind, "course": course})


def set_quiz(quiz: dict) -> None:
    """Vermerkt ein im Chat erstelltes Quiz (id/title/…), das der Prompt-Endpunkt
    als Meta an das Frontend mitschickt, damit es im Quiz-Tab geöffnet werden kann."""
    prov = current_provenance.get()
    if prov is not None and quiz:
        prov["quiz"] = quiz


def get_provenance() -> dict | None:
    return current_provenance.get()


def reset_trace_id(token) -> None:
    try:
        current_trace_id.reset(token)
    except (ValueError, LookupError):
        pass


def publish(
    event_type: str,
    node: str,
    label: str = "",
    detail: str = "",
    status: str = "",
    trace_id: str | None = None,
) -> None:
    """Publiziert ein Trace-Event an alle Abonnenten (fire-and-forget, nie werfend).

    event_type: chat_input | route | agent_start | agent_end | tool | rag | moodle | output | done | error
    node:       logischer Knoten, z.B. 'chat', 'orchestrator', 'tutor', 'rag', 'moodle', 'output'
    """
    try:
        event = {
            "seq": next(_seq),
            "ts": time.time(),
            "trace_id": trace_id or current_trace_id.get(),
            "type": event_type,
            "node": node,
            "label": label,
            "detail": (detail or "")[:600],
            "status": status,
        }
    except Exception:
        return

    _recent.append(event)
    if len(_recent) > _RECENT_MAX:
        del _recent[: len(_recent) - _RECENT_MAX]

    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass
        except Exception:
            pass


async def subscribe():
    """Async-Generator, der neue Events liefert (für die SSE-Schleife im Dashboard)."""
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    _subscribers.add(q)
    try:
        while True:
            yield await q.get()
    finally:
        _subscribers.discard(q)


def recent_events() -> list[dict]:
    return list(_recent)
