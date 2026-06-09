# Backend – KI-Lern- & Jobagent

Dieses Dokument erklärt den Aufbau des Backends und wie ihr es lokal zum Laufen bringt.

---

## Technologie-Stack

| Komponente | Technologie |
|---|---|
| API Framework | FastAPI |
| LLM | Google Gemini (`gemini-3.1-flash-lite-preview`) |
| Datenbank (relational) | PostgreSQL 16 |
| Vektordatenbank | ChromaDB |
| RAG / Embeddings | `pypdf`, `langchain-text-splitters`, Gemini Embeddings |
| Containerisierung | Docker |

---

## Ordnerstruktur

```
backend/
├── app/
│   ├── main.py                    # FastAPI Entry Point, Router-Registrierung, Lifespan
│   ├── core/
│   │   ├── config.py              # Einstellungen & Umgebungsvariablen
│   │   └── database.py            # SQLAlchemy Async Engine, get_db Dependency
│   ├── models/
│   │   ├── academic_event.py      # Planner-Deadlines (Prüfungen, Abgaben, Präsentationen)
│   │   ├── attempt_answer.py      # Einzelantworten eines Quiz-Versuchs
│   │   ├── calendar_event.py      # Stundenplan-Einträge (aus .ics importiert)
│   │   ├── chat.py                # ChatMessage (Prompt-Verlauf)
│   │   ├── document.py            # Hochgeladene PDFs
│   │   ├── exam.py                # Prüfungstermine
│   │   ├── grade.py               # Noteneinträge
│   │   ├── quiz.py                # Generierte Quizze
│   │   ├── quiz_attempt.py        # Quiz-Versuche mit Score
│   │   ├── quiz_question.py       # Einzelne Quizfragen (MC / TF)
│   │   ├── quiz_result.py         # Einfache Quiz-Ergebnisse (Legacy)
│   │   └── study_plan.py          # Lernpläne
│   ├── api/v1/
│   │   ├── prompt.py              # POST /api/prompt (Streaming-Chat)
│   │   ├── upload.py              # POST /api/upload, GET /api/documents
│   │   ├── history.py             # GET /api/history
│   │   ├── exams.py               # CRUD /api/exams
│   │   ├── calendar.py            # CRUD /api/calendar/events
│   │   ├── grades.py              # POST /api/grades/upload (→ n8n)
│   │   ├── job_agent.py           # POST /api/job-agent/run (→ n8n)
│   │   ├── planner.py             # CRUD /api/planner/events
│   │   ├── study_advisor.py       # POST /api/ai/study-advisor
│   │   └── tutor.py               # /api/tutor/* (Quiz-Generierung & Auswertung)
│   ├── services/
│   │   ├── planner_service.py     # Prioritäts-Berechnung für Events
│   │   ├── study_advisor_service.py  # KI-Lernberatung via Gemini + RAG
│   │   └── tutor_service.py       # Quiz-Generierung via Gemini + RAG
│   └── rag/
│       ├── store.py               # ChromaDB-Client & Gemini-Embedding-Hilfsklassen
│       ├── pipeline.py            # PDF → Text → Chunks → Embeddings → ChromaDB
│       └── retriever.py           # Query embedden → ChromaDB-Suche → Kontext-String
├── uploads/                       # Hochgeladene PDFs (wird automatisch erstellt)
├── tests/
├── .env                           # Lokale API-Keys (nicht ins Git!)
├── .env.example                   # Vorlage für .env
└── docker-compose.yml             # PostgreSQL & ChromaDB Container
```

---

## Voraussetzungen

- **Python 3.11+**
- **Docker Desktop** (muss im Hintergrund laufen)

---

## Setup – Schritt für Schritt

### 1. Virtuelle Python-Umgebung aktivieren

```bash
source .venv/bin/activate
```

### 2. Umgebungsvariablen einrichten

```bash
cp backend/.env.example backend/.env
```

`backend/.env` öffnen und ausfüllen:

```
GEMINI_API_KEY=AIza...
POSTGRES_URL=postgresql+asyncpg://agent_user:agent_pass@localhost:5432/agent_db
CHROMA_HOST=localhost
CHROMA_PORT=8000
N8N_JOB_AGENT_WEBHOOK_URL=http://...   # optional, für Job-Agent
```

> ⚠️ Die `.env` Datei niemals ins Git committen.

### 3. Datenbanken starten (Docker)

```bash
cd backend && docker compose up -d
```

Startet PostgreSQL (Port 5432) und ChromaDB (Port 8000).

### 4. Backend starten

```bash
source .venv/bin/activate
cd backend && uvicorn app.main:app --reload --port 8080
```

Beim ersten Start legt `create_all` alle Tabellen automatisch an.

---

## API-Endpunkte

### Chat & Upload

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/health` | Statuscheck |
| `POST` | `/api/prompt` | Streaming-Chat mit Gemini + RAG |
| `POST` | `/api/upload` | PDF hochladen, RAG-Pipeline anstoßen |
| `GET` | `/api/documents` | Liste aller hochgeladenen Dokumente (Dateinamen) |
| `GET` | `/api/history` | Letzte 50 Chat-Nachrichten |

### Kalender

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/api/calendar/events` | Alle Stundenplan-Einträge |
| `POST` | `/api/calendar/events` | Batch-Upsert (aus n8n .ics-Verarbeitung) |
| `DELETE` | `/api/calendar/events` | Alle Events löschen |
| `DELETE` | `/api/calendar/events/{id}` | Einzelnes Event löschen |

### Planner

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/api/planner/events` | Alle Deadlines |
| `GET` | `/api/planner/events/upcoming` | Nur zukünftige Deadlines |
| `POST` | `/api/planner/events` | Neue Deadline anlegen (EXAM / ASSIGNMENT / PRESENTATION) |
| `DELETE` | `/api/planner/events/{id}` | Deadline löschen |

### KI-Dienste

| Methode | URL | Beschreibung |
|---|---|---|
| `POST` | `/api/ai/study-advisor` | Lernberatung basierend auf Planner + Kalender |
| `POST` | `/api/grades/upload` | Notenübersicht-PDF → n8n → strukturierte Daten |
| `POST` | `/api/job-agent/run` | Job-Suche via n8n-Webhook starten |

### Tutor (Quiz)

| Methode | URL | Beschreibung |
|---|---|---|
| `POST` | `/api/tutor/quiz/generate` | Quiz aus hochgeladenen Dokumenten generieren |
| `GET` | `/api/tutor/quizzes` | Alle gespeicherten Quizze |
| `GET` | `/api/tutor/quiz/{id}` | Einzelnes Quiz mit Fragen laden |
| `POST` | `/api/tutor/quiz/{id}/submit` | Antworten einreichen, Score berechnen |
| `GET` | `/api/tutor/stats` | Stärken/Schwächen-Analyse über alle Versuche |

---

## RAG-Pipeline

Beim Hochladen einer PDF läuft automatisch im Hintergrund:

1. **Text extrahieren** – `pypdf` liest alle Seiten
2. **Chunken** – `langchain-text-splitters` teilt in überlappende Abschnitte (Standard: 1000 Zeichen, 150 Overlap)
3. **Embedden** – Gemini Embedding API (`gemini-embedding-001`)
4. **Speichern** – Upsert in ChromaDB mit `source`-Metadatum (Dateiname)

`retrieve_context(query, source_filter, n_results)` sucht relevante Chunks und gibt sie als formatierten Kontext-String zurück. `source_filter` schränkt die Suche auf bestimmte Dokumente ein (genutzt vom Tutor-Service).

---

## Umgebungsvariablen (`.env`)

| Variable | Pflicht | Beschreibung |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Google Gemini API Key |
| `POSTGRES_URL` | ✅ | AsyncPG Connection String |
| `CHROMA_HOST` | – | ChromaDB Host (Standard: `localhost`) |
| `CHROMA_PORT` | – | ChromaDB Port (Standard: `8000`) |
| `CHROMA_COLLECTION` | – | Collection-Name (Standard: `documents`) |
| `EMBEDDING_MODEL` | – | Gemini Embedding Modell (Standard: `gemini-embedding-001`) |
| `RAG_CHUNK_SIZE` | – | Chunk-Größe in Zeichen (Standard: `1000`) |
| `RAG_CHUNK_OVERLAP` | – | Überlappung in Zeichen (Standard: `150`) |
| `RAG_TOP_K` | – | Anzahl RAG-Treffer für Chat (Standard: `4`) |
| `N8N_JOB_AGENT_WEBHOOK_URL` | – | n8n Webhook für Job-Suche |