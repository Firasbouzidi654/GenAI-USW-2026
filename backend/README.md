# Backend – KI-Lern- & Jobagent

Dieses Dokument erklärt den Aufbau des Backends und wie ihr es lokal zum Laufen bringt.

---

## Technologie-Stack

| Komponente | Technologie |
|---|---|
| API Framework | FastAPI |
| Agent-Framework | LangChain 1.x + LangGraph |
| LLM | Google Gemini (`gemini-3.1-flash-lite-preview`) |
| Datenbank (relational) | PostgreSQL 16 |
| Vektordatenbank | ChromaDB |
| RAG / Embeddings | `pypdf`, `langchain-text-splitters`, Gemini Embeddings |
| Containerisierung | Docker |

> **Multi-Agent-System:** Die fachliche Logik liegt in echten LangChain-Agents
> (`app/agents/`), die autonom Tools aufrufen. Ein **Orchestrator** (Supervisor)
> koordiniert die vier Spezial-Agents. Übersicht: [Root-README](../README.md#architektur).

---

## Ordnerstruktur

```
backend/
├── app/
│   ├── main.py                    # FastAPI Entry Point, Router-Registrierung, Lifespan
│   ├── core/
│   │   ├── config.py              # Einstellungen & Umgebungsvariablen
│   │   └── database.py            # SQLAlchemy Async Engine, get_db Dependency
│   ├── agents/                    # ◀ Multi-Agent-System (LangChain 1.x / LangGraph)
│   │   ├── base.py                # LLM-Factory + Output-Extraktion (gemeinsam)
│   │   ├── orchestrator.py        # Supervisor: koordiniert & verkettet die 4 Agents
│   │   ├── tutor_agent.py         # RAG-Q&A + Quiz-Generierung (Structured Output)
│   │   ├── evaluator_agent.py     # Wissenslücken-Analyse aus Quiz-Ergebnissen
│   │   ├── planner_agent.py       # Lernpläne aus Kalender + Deadlines + Noten
│   │   └── career_agent.py        # Job-/Skill-Analyse aus dem Notenprofil
│   ├── models/
│   │   ├── academic_event.py      # Planner-Deadlines (Prüfungen, Abgaben, Präsentationen)
│   │   ├── attempt_answer.py      # Einzelantworten eines Quiz-Versuchs
│   │   ├── calendar_event.py      # Stundenplan-Einträge (aus LSF-Mock)
│   │   ├── chat.py                # ChatMessage (Prompt-Verlauf)
│   │   ├── document.py            # Hochgeladene PDFs
│   │   ├── exam.py                # Prüfungstermine
│   │   ├── grade.py               # Noteneinträge
│   │   ├── quiz.py                # Generierte Quizze
│   │   ├── quiz_attempt.py        # Quiz-Versuche mit Score
│   │   └── quiz_question.py       # Einzelne Quizfragen (MC / TF)
│   ├── api/v1/
│   │   ├── prompt.py              # POST /api/prompt (Orchestrator-Chat, Streaming)
│   │   ├── upload.py              # POST /api/upload, GET /api/documents
│   │   ├── history.py             # GET /api/history
│   │   ├── lsf_mock.py            # ◀ LSF-Mock: /api/lsf/* (Module, Noten, Termine, Sync)
│   │   ├── exams.py               # GET /api/exams (read-only)
│   │   ├── calendar.py            # GET /api/calendar/events (read-only)
│   │   ├── grades.py              # GET /api/grades (read-only)
│   │   ├── planner.py             # GET /api/planner/events (read-only)
│   │   ├── study_advisor.py       # POST /api/ai/study-advisor → PlannerAgent
│   │   ├── evaluator.py           # /api/ai/evaluate, /api/ai/knowledge-gaps → EvaluatorAgent
│   │   ├── career.py              # GET /api/career/analysis → CareerAgent
│   │   └── tutor.py               # /api/tutor/* (Quiz-Generierung & Auswertung)
│   ├── services/
│   │   ├── lsf_sync.py            # ◀ LSF-Mock → DB-Tabellen (idempotent)
│   │   ├── planner_service.py     # Prioritäts-Berechnung für Events (von PlannerAgent genutzt)
│   │   └── tutor_service.py       # Brücke: validiert & speichert Quiz vom TutorAgent
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
POSTGRES_URL=postgresql+asyncpg://agent_user:agent_pass@localhost:5433/agent_db
CHROMA_HOST=localhost
CHROMA_PORT=8000
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

Beim ersten Start legt `create_all` alle Tabellen automatisch an und der
**LSF-Auto-Seed** befüllt sie mit Noten, Terminen, Prüfungen und Stundenplan.

---

## API-Endpunkte

### Chat & Upload

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/health` | Statuscheck |
| `POST` | `/api/prompt` | Streaming-Chat über den **Orchestrator** (routet zu allen Agents) |
| `POST` | `/api/upload` | PDF hochladen, RAG-Pipeline anstoßen |
| `GET` | `/api/documents` | Liste aller hochgeladenen Dokumente (Dateinamen) |
| `GET` | `/api/history` | Letzte 50 Chat-Nachrichten |

### LSF-Mock (Datenquelle für Noten & Termine)

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/api/lsf/modules` | Belegte Module (Stammdaten) |
| `GET` | `/api/lsf/grades` | Noten der abgeschlossenen Module |
| `GET` | `/api/lsf/termine` | Alle Termine (Vorlesungen, Prüfungen, Abgaben, Präsentationen) |
| `GET` | `/api/lsf/exams` | Nur Prüfungstermine |
| `POST` | `/api/lsf/sync` | LSF-Daten idempotent in die DB übernehmen |

### Read-only Anzeige (aus DB, befüllt durch LSF-Sync)

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/api/grades` | Noten |
| `GET` | `/api/calendar/events` | Stundenplan-Einträge |
| `GET` | `/api/planner/events` | Alle Deadlines |
| `GET` | `/api/planner/events/upcoming` | Nur zukünftige Deadlines |
| `GET` | `/api/exams` | Prüfungstermine |

### KI-Dienste

| Methode | URL | Agent / Beschreibung |
|---|---|---|
| `POST` | `/api/ai/study-advisor` | **PlannerAgent** — Lernplan aus Planner + Kalender + Noten |
| `POST` | `/api/ai/evaluate` | **EvaluatorAgent** — konversationelle Lernfortschritts-Analyse |
| `GET` | `/api/ai/knowledge-gaps` | **EvaluatorAgent** — vollständige Wissenslücken-Analyse |
| `GET` | `/api/career/analysis` | **CareerAgent** — strukturierte Job-/Skill-Analyse (Structured Output) |

### Tutor (Quiz)

| Methode | URL | Beschreibung |
|---|---|---|
| `POST` | `/api/tutor/quiz/generate` | Quiz aus hochgeladenen Dokumenten generieren |
| `POST` | `/api/tutor/quiz/weakness` | **Schwächen-Quiz** aus den schwachen Themen des Profils |
| `GET` | `/api/tutor/quizzes` | Alle gespeicherten Quizze |
| `GET` | `/api/tutor/quiz/{id}` | Einzelnes Quiz mit Fragen laden |
| `POST` | `/api/tutor/quiz/{id}/submit` | Antworten einreichen, Score berechnen |
| `GET` | `/api/tutor/stats` | Stärken/Schwächen-Analyse über alle Versuche |
| `DELETE` | `/api/tutor/stats` | **Statistiken zurücksetzen** (Versuche + Antworten löschen) |
| `GET` | `/api/tutor/profile` | **Lernprofil**: pro Thema ein Score 0–100 aus den Quiz-Ergebnissen |

### Profil

| Methode | URL | Beschreibung |
|---|---|---|
| `POST` | `/api/profile/reset` | **Alle Nutzerdaten zurücksetzen**: Quizze, Versuche, Dokumente (inkl. Vektor-DB), Lebenslauf, Modulhandbuch und eigene Kalendertermine |

### Career & CV

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/api/career/analysis` | KI-Karriereanalyse (Noten + optional CV) |
| `POST` | `/api/career/cv` | **Lebenslauf (PDF) hochladen** → Text fließt in die Analyse ein |
| `GET` / `DELETE` | `/api/career/cv` | CV-Status / CV entfernen |

### Moodle (HTW, optional — Token nötig)

| Methode | URL | Beschreibung |
|---|---|---|
| `GET` | `/api/moodle/status` | Ob ein Moodle-Token konfiguriert ist |
| `GET` | `/api/moodle/courses` | Belegte Kurse, nach Semester sortiert |
| `POST` | `/api/moodle/index` | Materialien eines Kurses on-demand in die RAG indizieren |

> Der Tutor-Agent nutzt Moodle **automatisch**: findet er in den hochgeladenen
> Dokumenten nichts, listet er die belegten Kurse, indiziert den passenden Kurs
> und sucht erneut. Token in `backend/.env` als `MOODLE_TOKEN` hinterlegen.

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