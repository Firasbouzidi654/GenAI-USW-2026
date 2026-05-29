# Backend – KI-Lern- & Jobagent

Dieses Dokument erklärt den Aufbau des Backends und wie ihr es lokal zum Laufen bringt.

---

## Technologie-Stack

| Komponente | Technologie |
|---|---|
| API Framework | FastAPI |
| LLM | Google Gemini (`gemini-2.5-flash`) |
| Datenbank (relational) | PostgreSQL 16 |
| Vektordatenbank | ChromaDB |
| Agenten-Framework | LangGraph |
| RAG / Embeddings | LangChain |
| Containerisierung | Docker |

---

## Ordnerstruktur

```
backend/
├── app/
│   ├── main.py               # FastAPI Entry Point, Router-Registrierung, Lifespan
│   ├── core/
│   │   ├── config.py         # Einstellungen & Umgebungsvariablen
│   │   └── database.py       # SQLAlchemy Async Engine, get_db Dependency
│   ├── models/
│   │   ├── chat.py           # ChatMessage Tabelle (Prompt-Verlauf)
│   │   └── document.py       # Document Tabelle (hochgeladene PDFs)
│   ├── api/
│   │   └── v1/
│   │       ├── prompt.py     # POST /api/prompt, POST /api/prompt/stream
│   │       └── upload.py     # POST /api/upload
│   ├── agents/
│   │   ├── tutor_agent.py    # LangGraph Tutor-Agent (Modul A)
│   │   └── job_agent.py      # Job-Matching & Anschreiben (Modul B)
│   ├── mcp_servers/
│   │   ├── htw_integration.py      # HTW Noten, Termine, Module
│   │   ├── job_portal_gateway.py   # LinkedIn, StepStone, Indeed
│   │   └── file_bridge.py          # PDF Parsing & Verwaltung
│   └── rag/
│       ├── pipeline.py       # Stub: Chunking & Embedding (→ Laszlo)
│       └── retriever.py      # Stub: Vektor-Suche & Kontext-Abruf (→ Laszlo)
├── uploads/                  # Hochgeladene PDFs (wird automatisch erstellt)
├── tests/
├── .env                      # Eure lokalen API-Keys (nicht ins Git!)
├── .env.example              # Vorlage für .env
└── docker-compose.yml        # PostgreSQL & ChromaDB Container
```

---

## Voraussetzungen

- **Python 3.11+**
- **Node.js 18+** (für das Frontend)
- **Docker Desktop** (muss im Hintergrund laufen)

---

## Setup – Schritt für Schritt

### 1. Repository klonen

```bash
git clone <repo-url>
cd <repo-ordner>
```

### 2. Virtuelle Python-Umgebung erstellen & aktivieren

```bash
python3 -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Abhängigkeiten installieren

```bash
pip install fastapi uvicorn pydantic-settings \
            sqlalchemy asyncpg greenlet \
            chromadb langchain \
            google-genai \
            python-multipart python-dotenv \
            pytest pytest-asyncio httpx
```

### 4. Umgebungsvariablen einrichten

```bash
cp backend/.env.example backend/.env
```

Dann `backend/.env` öffnen und ausfüllen:

```
GEMINI_API_KEY=AIza...
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

Startet PostgreSQL (Port 5432) und ChromaDB (Port 8000) als Hintergrundprozesse.

### 6. Backend starten

ChromaDB belegt Port 8000, daher läuft das Backend auf Port **8080**:

```bash
cd backend
uvicorn app.main:app --reload --port 8080
```

### 7. Frontend starten

```bash
cd frontend
npm install   # nur beim ersten Mal
npm run dev
```

Frontend ist dann erreichbar unter: **http://localhost:5173**

---

## API-Endpunkte

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/health` | Statuscheck |
| `GET` | `/docs` | Interaktive API-Dokumentation (Swagger UI) |
| `POST` | `/api/prompt` | Prompt an Gemini senden, Antwort erhalten |
| `POST` | `/api/prompt/stream` | Prompt streamen (Server-Sent Events) |
| `POST` | `/api/upload` | PDF hochladen und RAG-Pipeline anstoßen |

### POST `/api/prompt`

Request:
```json
{ "prompt": "Was ist eine SQL JOIN-Operation?" }
```

Response:
```json
{ "response": "Eine JOIN-Operation verbindet..." }
```

Fehlercodes: `422` bei fehlendem Feld, `502` wenn Gemini nicht erreichbar ist.

### POST `/api/prompt/stream`

Gleicher Request-Body wie `/api/prompt`. Gibt einen `text/event-stream` zurück — Antwort kommt Stück für Stück an:

```
data: Eine JOIN-
data: Operation verbindet...
data: [DONE]
```

### POST `/api/upload`

Multipart-Form mit einem Feld `file` (nur PDF erlaubt).

```bash
curl -X POST http://localhost:8080/api/upload \
     -F "file=@skript.pdf"
```

Response:
```json
{ "status": "ok", "filename": "skript.pdf" }
```

Fehlercodes: `400` bei Nicht-PDF oder ungültigem Dateinamen, `500` bei Speicherfehler.

---

## RAG-Pipeline (Laszlo)

Die Endpunkte rufen zwei Stubs auf, die noch implementiert werden müssen:
    
| Datei | Funktion | Aufgabe |
|---|---|---|
| `app/rag/pipeline.py` | `process_document(file_path)` | PDF parsen, chunken, embedden, in ChromaDB speichern |
| `app/rag/retriever.py` | `retrieve_context(query)` | Query embedden, ChromaDB durchsuchen, Kontext als String zurückgeben |

Sobald diese beiden Funktionen implementiert sind, nutzen `/api/prompt` und `/api/upload` sie automatisch.

---

## Architektur-Überblick

**Modul A – Adaptiver Lernagent**
Verarbeitet hochgeladene Vorlesungs-PDFs über eine RAG-Pipeline (Chunking → Embeddings → ChromaDB). Der LangGraph-Tutor-Agent generiert dynamisch Quizzes und schaltet bei schlechter Performance automatisch auf alternative Lernressourcen um.

**Modul B – KI-Jobsuche & Karriereagent**
Vergleicht Lebenslauf-Vektoren semantisch mit Stellenanzeigen und generiert individuelle Anschreiben basierend auf den Studienmodulen des Nutzers.

**MCP-Server-Infrastruktur**
Drei spezialisierte Server kapseln externe Schnittstellen: HTW-Systeme (Noten, Prüfungstermine), Job-Portale (LinkedIn, StepStone) und das lokale Dateisystem.