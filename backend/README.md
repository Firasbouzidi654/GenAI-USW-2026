# Backend – KI-Lern- & Jobagent

Dieses Dokument erklärt den Aufbau des Backends und wie ihr es lokal zum Laufen bringt.

---

## Technologie-Stack

| Komponente | Technologie |
|---|---|
| API Framework | FastAPI |
| Datenbank (relational) | PostgreSQL 16 |
| Vektordatenbank | ChromaDB |
| Agenten-Framework | LangGraph |
| RAG / Embeddings | LangChain + OpenAI |
| Containerisierung | Docker |

---

## Ordnerstruktur

```
backend/
├── app/
│   ├── main.py               # FastAPI Entry Point
│   ├── core/
│   │   ├── config.py         # Einstellungen & Umgebungsvariablen
│   │   └── database.py       # DB-Verbindungen (PostgreSQL & Chroma)
│   ├── api/
│   │   └── v1/
│   │       ├── learning.py   # Endpunkte: /learning/*
│   │       └── jobs.py       # Endpunkte: /jobs/*
│   ├── agents/
│   │   ├── tutor_agent.py    # LangGraph Tutor-Agent (Modul A)
│   │   └── job_agent.py      # Job-Matching & Anschreiben (Modul B)
│   ├── mcp_servers/
│   │   ├── htw_integration.py      # HTW Noten, Termine, Module
│   │   ├── job_portal_gateway.py   # LinkedIn, StepStone, Indeed
│   │   └── file_bridge.py          # PDF Parsing & Verwaltung
│   └── rag/
│       ├── pipeline.py       # Chunking & Embedding-Generierung
│       └── retriever.py      # Vektor-Suche & Kontext-Abruf
├── tests/
├── .env                      # Eure lokalen API-Keys (nicht ins Git!)
├── .env.example              # Vorlage für .env
├── docker-compose.yml        # PostgreSQL & ChromaDB Container
└── pyproject.toml
```

---

## Voraussetzungen

Stellt sicher, dass folgendes auf eurem Rechner installiert ist:

- **Python 3.11+** – [python.org](https://www.python.org/downloads/)
- **Docker Desktop** – [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) (muss im Hintergrund laufen)
- **Git**

---

## Setup – Schritt für Schritt

### 1. Repository klonen

```bash
git clone <repo-url>
cd <repo-ordner>
```

### 2. Virtuelle Python-Umgebung erstellen & aktivieren

```bash
# Umgebung erstellen
python3 -m venv .venv

# Aktivieren (macOS/Linux)
source .venv/bin/activate

# Aktivieren (Windows)
.venv\Scripts\activate
```

### 3. Abhängigkeiten installieren

```bash
pip install fastapi uvicorn pydantic-settings asyncpg \
            sqlalchemy chromadb langchain langchain-openai \
            python-multipart python-dotenv
```

### 4. Umgebungsvariablen einrichten

Kopiert die Vorlage und tragt eure API-Keys ein:

```bash
cp backend/.env.example backend/.env
```

Dann `.env` öffnen und ausfüllen:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
POSTGRES_URL=postgresql+asyncpg://agent_user:agent_pass@localhost:5432/agent_db
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

> ⚠️ Die `.env` Datei niemals ins Git committen – sie ist in `.gitignore` eingetragen.

### 5. Datenbanken starten (Docker)

```bash
cd backend
docker compose up -d
```

Das startet PostgreSQL (Port 5432) und ChromaDB (Port 8000) als Hintergrundprozesse.

### 6. Backend starten

```bash
cd backend
uvicorn app.main:app --reload
```

---

## Testen ob alles läuft

| URL                          | Erwartetes Ergebnis |
|------------------------------|---|
| http://127.0.0.1:8080/health | `{"status": "ok"}` |
| http://127.0.0.1:8080/docs   | Interaktive API-Dokumentation |

---

## Architektur-Überblick

Das Backend besteht aus drei Hauptbereichen:

**Modul A – Adaptiver Lernagent**
Verarbeitet hochgeladene Vorlesungs-PDFs über eine RAG-Pipeline (Chunking → Embeddings → ChromaDB). Der LangGraph-Tutor-Agent generiert dynamisch Quizzes und schaltet bei schlechter Performance automatisch auf alternative Lernressourcen um.

**Modul B – KI-Jobsuche & Karriereagent**
Vergleicht Lebenslauf-Vektoren semantisch mit Stellenanzeigen und generiert individuelle Anschreiben basierend auf den Studienmodulen des Nutzers.

**MCP-Server-Infrastruktur**
Drei spezialisierte Server kapseln externe Schnittstellen: HTW-Systeme (Noten, Prüfungstermine), Job-Portale (LinkedIn, StepStone) und das lokale Dateisystem.

---

