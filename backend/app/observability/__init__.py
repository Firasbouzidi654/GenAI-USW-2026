"""Observability (nur für Präsentation) — Live-Trace des Agenten-Flows.

Dieses Paket ist bewusst KEIN Teil der Kern-Anwendung. Die Agenten publizieren an
einen In-Process-Event-Bus; ein separates Dashboard (eigener Port) abonniert die
Events und zeichnet den Live-Flow (Chat → Orchestrator → Agent → Tools/RAG → Output).
Wenn niemand abonniert, sind die publish()-Aufrufe praktisch kostenlos.
"""
