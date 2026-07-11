"""Startet das Observability-Dashboard als zweiten uvicorn-Server im selben Prozess.

So teilt es sich den In-Process-Event-Bus mit dem Backend, läuft aber auf einem
eigenen Port. Wird aus der Lifespan des Haupt-Backends gestartet, wenn
OBSERVABILITY_ENABLED gesetzt ist.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_server = None
_task: asyncio.Task | None = None


async def start(port: int) -> None:
    global _server, _task
    if _task is not None:
        return
    try:
        import uvicorn

        from app.observability.dashboard import dashboard_app

        config = uvicorn.Config(dashboard_app, host="0.0.0.0", port=port, log_level="warning")
        _server = uvicorn.Server(config)
        _server.install_signal_handlers = lambda: None  # kein eigenes Signal-Handling
        _task = asyncio.create_task(_server.serve())
        logger.info("Observability-Dashboard läuft auf http://localhost:%s", port)
    except Exception as exc:
        logger.warning("Observability-Dashboard konnte nicht gestartet werden: %s", exc)


async def stop() -> None:
    global _server, _task
    if _server is not None:
        _server.should_exit = True
    if _task is not None:
        try:
            await asyncio.wait_for(_task, timeout=5)
        except (asyncio.TimeoutError, Exception):
            _task.cancel()
    _server, _task = None, None
