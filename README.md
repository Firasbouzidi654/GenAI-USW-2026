# Adaptive Study & Career Agent

Ein KI-gestütztes **Multi-Agent-System**, das Studierenden hilft, effektiver zu lernen und sich gleichzeitig auf Praktika und Jobs vorzubereiten.

Studierende laden ihr Lernmaterial hoch und stellen Fragen dazu. Ein **Supervisor-Agent** koordiniert im Hintergrund vier spezialisierte Agents, die untereinander zusammenarbeiten.

> **Die Grundidee:** Je besser du lernst, desto bessere Karrierechancen kann dir das System aufzeigen.

---

## Architektur

```
                         ┌───────────────────────────┐
   User (Frontend) ─────▶│   Orchestrator-Agent       │  Supervisor
                         │   (entscheidet & verkettet) │
                         └────────────┬───────────────┘
                                      │ ruft Spezial-Agents als Tools auf
            ┌───────────────┬─────────┼──────────────┬────────────────┐
            ▼               ▼         ▼               ▼
     ┌───────────┐  ┌────────────┐ ┌──────────┐ ┌──────────┐
     │  Tutor    │  │ Evaluator  │ │ Planner  │ │ Career   │
     │  Agent    │  │  Agent     │ │  Agent   │ │  Agent   │
     └─────┬─────┘  └─────┬──────┘ └────┬─────┘ └────┬─────┘
           │ Tools        │ Tools       │ Tools      │ Tools
           ▼              ▼             ▼            ▼
     RAG / ChromaDB   Quiz-Statistik  Kalender +   Noten /
     (Lernmaterial)   (PostgreSQL)    Deadlines    Transcript
```

### Die Agents (LangChain 1.x / LangGraph)

| Agent | Aufgabe | Tools |
|---|---|---|
| **Orchestrator** | Supervisor: nimmt jede Chat-Anfrage entgegen, wählt den/die passenden Spezial-Agent(en) und **verkettet** sie (z.B. Evaluator findet Lücke → Tutor erklärt das Thema) | die 4 Agents als Tools |
| **Tutor** | Beantwortet Fragen zum Lernmaterial (RAG), erklärt Konzepte, generiert Quizze | Dokumentensuche, Volltextsuche pro Dokument, Quiz-Generierung (Structured Output) |
| **Evaluator** | Erkennt Wissenslücken aus Quiz-Ergebnissen | Gesamtstatistik, schwache Fragen, letzte Versuche, Fragetyp-Analyse |
| **Planner** | Erstellt Lernpläne rund um den Stundenplan | Deadlines, Kalender-Stundenplan, Notenübersicht |
| **Career** | Empfiehlt Jobs & Lernpfade aus dem Notenprofil | Notenblatt, starke Fächer, schwache Fächer + Structured-Output-Analyse |

So „reden die Agents miteinander": Der Orchestrator ruft sie als Tools auf, reicht Zwischenergebnisse weiter und fasst alles zu einer Antwort zusammen.

---

## Tech-Stack

| Ebene | Technologie |
|---|---|
| Frontend | Vue 3 + Vite |
| Backend | FastAPI (Python 3.11+) |
| Agent-Framework | LangChain 1.x + LangGraph |
| LLM | Google Gemini (`gemini-3.1-flash-lite-preview`) |
| Relationale DB | PostgreSQL 16 |
| Vektor-DB (RAG) | ChromaDB |
| Embeddings | Gemini (`gemini-embedding-001`) |

---

## Voraussetzungen

Bevor du startest, brauchst du:

1. **Python 3.11+** (das mitgelieferte `.venv` nutzt 3.13)
2. **Node.js 18+** (für das Vue-Frontend)
3. **Docker Desktop** (für PostgreSQL + ChromaDB) — muss laufen
4. **Google Gemini API Key** — kostenlos unter <https://aistudio.google.com/app/apikey>
   - Stelle sicher, dass dein Key Zugriff auf das Modell `gemini-3.1-flash-lite-preview` hat

> Der Code nutzt **ausschließlich** den Gemini-Key. `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` in der `.env` sind optional und werden aktuell nicht verwendet. **Kein n8n, keine weiteren externen Dienste nötig** — Noten und Termine liefert der eingebaute LSF-Mock.

---

## Schnellstart

### 1. Umgebungsvariablen

```bash
cd backend
cp .env.example .env
```

Öffne `backend/.env` und trage mindestens deinen Gemini-Key ein:

```env
GEMINI_API_KEY=AIza...                                                   # PFLICHT
POSTGRES_URL=postgresql+asyncpg://agent_user:agent_pass@localhost:5433/agent_db
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

> ⚠️ Die `.env` niemals ins Git committen.

### 2. Datenbanken starten (Docker)

```bash
cd backend
docker compose up -d
```

Startet **PostgreSQL** (Port 5432) und **ChromaDB** (Port 8000).

### 3. Backend starten

```bash
cd backend
pip install -r requirements.txt        # einmalig (oder: uv pip install -r requirements.txt)
uvicorn app.main:app --reload --port 8080
```

Beim ersten Start legt SQLAlchemy automatisch alle Tabellen an.
API-Doku dann unter <http://localhost:8080/docs>.

### 4. Frontend starten

```bash
cd frontend
npm install        # einmalig
npm run dev
```

Frontend läuft auf <http://localhost:5173> und proxyt `/api` → `http://localhost:8080`.

---

## Datenquelle: LSF-Mock

Noten, Termine, Prüfungen und der Stundenplan kommen **nicht** aus manueller Eingabe,
sondern aus einem eingebauten **LSF-Mock** (`/api/lsf/...`), der das LSF-System der
HTW nachbildet. Beim Backend-Start werden diese Daten automatisch idempotent in die
Datenbank geladen (Auto-Seed). Im Frontend lädt der Button **„🔄 LSF synchronisieren"**
(oben in der Navbar) die Daten jederzeit neu.

| LSF-Mock | → DB-Tabelle | → Tab im Frontend |
|---|---|---|
| Noten | `grades` | Noten / Career |
| Termine (Vorlesungen/Übungen) | `calendar_events` | Kalender |
| Termine (Prüfungen/Abgaben/Präsentationen) | `academic_events` | Planner |
| Termine (Prüfungen) | `exams` | Prüfungen |

---

## Benutzung

1. **„🔄 LSF synchronisieren"** klicken → Noten, Termine, Prüfungen, Kalender werden geladen.
2. **Material hochladen** → PDF wird per RAG indiziert (ChromaDB).
3. **Fragen stellen** im Chat → der Orchestrator routet automatisch zum passenden Agent.
4. **Quiz generieren** (Tutor) → beantworten → Score wird gespeichert.
5. **„🧠 KI-Wissenslücken-Analyse"** im Statistik-Tab → der Evaluator-Agent wertet alle Versuche aus.
6. **Lernplan** anfragen → der Planner-Agent plant um deinen Stundenplan herum.
7. **Karriere-Tab** → der Career-Agent analysiert deine Noten und empfiehlt Jobs + Lernpfade.

---

## Tests

```bash
cd backend
PYTHONPATH=. pytest          # 49 Tests, keine API-Keys / DB nötig (alles gemockt)
```

---

## Wichtige Endpunkte

| Methode | URL | Agent / Funktion |
|---|---|---|
| `POST` | `/api/prompt` | **Orchestrator** (Streaming-Chat, routet zu allen Agents) |
| `POST` | `/api/tutor/quiz/generate` | **Tutor** — Quiz aus Dokumenten |
| `GET` | `/api/tutor/stats` | Quiz-Statistik (Rohdaten) |
| `POST` | `/api/ai/evaluate` | **Evaluator** — konversationell |
| `GET` | `/api/ai/knowledge-gaps` | **Evaluator** — volle Wissenslücken-Analyse |
| `POST` | `/api/ai/study-advisor` | **Planner** — Lernplan |
| `GET` | `/api/career/analysis` | **Career** — strukturierte Job-/Skill-Analyse |
| `POST` | `/api/upload` | PDF hochladen → RAG-Pipeline |
| `POST` | `/api/lsf/sync` | **LSF-Mock** → DB synchronisieren (Noten, Termine, Prüfungen, Kalender) |
| `GET` | `/api/grades`, `/api/calendar/events`, `/api/planner/events`, `/api/exams` | Read-only Anzeige (aus DB) |

Vollständige Backend-Doku: [`backend/README.md`](backend/README.md).

---

## Troubleshooting

| Problem | Ursache / Lösung |
|---|---|
| `RESOURCE_EXHAUSTED` / 429 | Gemini-Kontingent erschöpft oder Modell nicht freigeschaltet. Warte kurz oder prüfe dein Quota in AI Studio. |
| `ChromaDB nicht erreichbar` | `docker compose up -d` vergessen, oder Port 8000 belegt. RAG fällt dann sauber auf „kein Kontext" zurück. |
| `Datenbank nicht erreichbar` / `Connection refused` / `InvalidAuthorization` auf 5432 | Häufig läuft schon ein **lokaler Postgres auf 5432**, der den Docker-Container verdeckt. Deshalb nutzt das Projekt **Port 5433** (docker-compose + `.env`). Nach Änderung des Ports den Container neu erstellen: `cd backend && docker compose up -d`. |
| Chat antwortet generisch ohne Material | Dokument war noch nicht fertig indiziert — direkt nach dem Upload ein paar Sekunden warten (Embeddings laufen im Hintergrund). |

## Chats & Dokument-Isolation

Jeder Browser hat eine persistente **`chat_id`** (in `localStorage`). Hochgeladene
PDFs werden in der Vektor-DB (ChromaDB) mit `chat_id` **und** `user_id` als Metadaten
abgelegt; bei jeder Frage filtert der Tutor-Agent auf genau diese Werte. So vermischen
sich Dokumente verschiedener Chats nicht mehr. Über **„＋ Neuer Chat"** (Navbar) startet
man einen frischen Chat mit eigener `chat_id` (eigene Dokumente, leerer Verlauf). Die
`user_id` (Default `local`) ist bereits durchgereicht und vorbereitet für späteren
Multi-User-Betrieb.
