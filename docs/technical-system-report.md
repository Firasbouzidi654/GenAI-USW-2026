# Technical System Report

This document explains how the project works end to end. It is written as an
onboarding guide for a developer joining the codebase.

## 1. High-Level Architecture

```text
Vue frontend
  |
  | fetch('/api/...')
  v
FastAPI backend
  |
  +-- SQLAlchemy async session -> PostgreSQL tables
  +-- RAG pipeline -> ChromaDB vector collection
  +-- Gemini / Groq LLM providers through LangChain
  +-- Moodle REST API through moodle_service.py
  +-- n8n webhook through job_agent.py
  +-- external job APIs through job_service.py
```

The frontend is a single Vue app in `frontend/src/App.vue`. It stores local UI
state such as chats, messages, theme, selected Moodle course, and study plan in
`localStorage`. The backend is a FastAPI app in `backend/app/main.py`. It mounts
versioned API routers under `/api` and exposes `/health`.

Persistent app state lives in PostgreSQL through SQLAlchemy models in
`backend/app/models`. Semantic document search lives in ChromaDB through
`backend/app/rag`. LLM reasoning is concentrated in `backend/app/agents`.

## 2. AI Agents

### Orchestrator Agent

File: `backend/app/agents/orchestrator.py`

Responsibility: supervisor. It decides whether a user prompt should be answered
by deterministic Moodle helpers, Tutor, Planner, Evaluator, Career, or
Curriculum.

Main functions:

- `should_route_to_moodle_context(message)`
  - Called by `run_orchestrator` and `study_advisor`.
  - Input: user message.
  - Output: boolean.
  - Logic: checks Moodle keywords and deterministic semester-course patterns.
  - Failure mode: false negatives route Moodle questions to the LLM supervisor;
    false positives bypass the supervisor.

- `create_orchestrator(db, chat_id, user_id, moodle_context, llm)`
  - Called by `run_orchestrator` via `run_agent_with_model_fallback`.
  - Output: LangGraph React agent.
  - Tools exposed to the LLM:
    - `ask_tutor`
    - `ask_evaluator`
    - `ask_planner`
    - `ask_career`
    - `ask_curriculum`
  - Database: passes the active SQLAlchemy session into tools.

- `run_orchestrator(message, db, chat_id, user_id, moodle_context)`
  - Called by `/api/prompt`.
  - Logic:
    1. If the message references the selected Moodle material, directly call
       Tutor with `moodle_context`.
    2. If it is deterministic Moodle context, call
       `get_moodle_context_for_message`.
    3. Otherwise run the supervisor agent.
    4. Extract the final assistant text with `extract_text_output`.
  - Errors: logs and returns a friendly unavailable message.

### Tutor Agent

File: `backend/app/agents/tutor_agent.py`

Responsibility: answer learning-material questions, selected Moodle-material
questions, direct concept questions, generate quizzes, and generate quiz reviews.

Main functions:

- `_needs_material_context(message)`
  - Called by `run_tutor_agent`.
  - Determines if the question mentions PDFs, uploaded files, Moodle, slides,
    material, sources, etc.

- `_is_selected_moodle_material_request(message, moodle_context)`
  - Called by Orchestrator and Tutor.
  - Determines if the user is asking about currently selected Moodle material.
  - Improved in this pass: matching now normalizes punctuation, accents, and
    leading zeros, so `Session 1` can match `Session 01`.

- `_matching_moodle_files(message, moodle_context)`
  - Input: user message plus frontend-provided Moodle overview.
  - Output: list of file dicts `{filename, fileurl, module, section}`.
  - Uses section name, item name, and filename matching.
  - Failure mode: weak labels or missing file URLs can prevent RAG grounding.

- `_load_matching_moodle_files_from_service(message, moodle_context)`
  - Calls `moodle_service.get_course_files(course_id)` if frontend context lacks
    file URLs.
  - External service: Moodle REST API.
  - Errors: logs and returns `[]`.

- `_ensure_moodle_files_indexed(files, moodle_context, chat_id, user_id, metadata_filter)`
  - Downloads matching Moodle files and indexes extracted text into ChromaDB.
  - Uses:
    - `moodle_service.download_file_text`
    - `rag.pipeline.index_text`
    - `rag.retriever.has_indexed_source`
  - Output: `(indexed_file_count, chunk_count)`.
  - Failure mode: unreadable file, unsupported format, expired Moodle token,
    Chroma unavailable, embedding failure. It skips bad files and continues.

- `_answer_from_selected_moodle_material(message, chat_id, user_id, moodle_context)`
  - Step by step:
    1. Find matching Moodle files from frontend context.
    2. Fetch live Moodle file data if URLs are missing.
    3. Try retrieving existing indexed chunks from Chroma.
    4. If missing, download and index matching files.
    5. Retrieve again.
    6. Send context to the LLM with `_MOODLE_RAG_SYSTEM_PROMPT`.
  - Output: grounded answer string.
  - Errors: if no context can be found, returns a precise "not indexed/readable"
    message; LLM failures return a friendly unavailable message.

- `create_tutor_agent(db, chat_id, user_id, llm)`
  - Tools:
    - `search_learning_material(query)` -> RAG across user documents.
    - `search_in_document(document_name, query)` -> RAG for one source.
    - `list_available_documents()` -> DB `documents`.
    - `list_moodle_courses()` -> Moodle courses.
    - `index_moodle_course(course_name)` -> Moodle download and indexing.

- `run_tutor_agent(message, db, chat_id, user_id, moodle_context)`
  - If selected Moodle material: use direct Moodle RAG path.
  - If no material context needed: direct LLM answer, no tools.
  - Otherwise: run Tutor React agent with tools.

- `generate_quiz_with_agent(source_documents, num_questions, db, course_name, chat_id, user_id)`
  - Gets broad RAG context from selected docs.
  - Uses structured output schema `_QuizSchema`.
  - Has JSON fallback for providers that return malformed structured output.
  - Output: `{title, questions}`.
  - Errors: no indexed context -> `ValueError`; LLM failure -> `RuntimeError`.

- `generate_quiz_review(...)`
  - Retrieves context for wrong answers.
  - Sends quiz result plus wrong-answer block to LLM.
  - Output: Markdown review.

### Planner Agent

File: `backend/app/agents/planner_agent.py`

Responsibility: learning plans and deadline/schedule reasoning.

Tools:

- `get_upcoming_deadlines()` -> DB `academic_events`.
- `get_calendar_schedule(days_ahead)` -> DB `calendar_events`.
- `get_grade_summary()` -> DB `grades`.
- `get_moodle_deadlines(course_name)` -> `moodle_context_service`.
- `get_moodle_courses()` -> `moodle_context_service`.

Entry point: `run_planner_agent(message, db)`.

Logic: build a React agent with planning tools, run it through model fallback,
then format final output. It also has formatting fallbacks for raw JSON/tool
outputs.

### Evaluator Agent

File: `backend/app/agents/evaluator_agent.py`

Responsibility: learning-progress and weakness analysis.

Tools:

- `get_overall_quiz_statistics()` -> `quiz_attempts`.
- `get_weak_questions(limit)` -> `quiz_attempt_answers`, `quiz_questions`.
- `get_recent_attempts(limit)` -> recent attempts.
- `get_question_type_breakdown()` -> MC/TF performance.
- `find_prerequisites(module_name)` -> `curriculum_modules`.
- `list_curriculum_modules()` -> `curriculum_modules`.
- `get_moodle_grades(course_name)` -> Moodle grades context.

Entry points:

- `run_evaluator_agent(message, db)`
- `get_knowledge_gap_analysis(db)`

Errors: DB/tool exceptions are caught in each tool and returned as readable text;
agent-level failure returns a service-unavailable style message.

### Career Agent

File: `backend/app/agents/career_agent.py`

Responsibility: career fit, skills, roles, learning path, and job suggestions
from grades, CV, Moodle grades, and quiz performance.

Tools:

- `get_academic_transcript()` -> DB `grades`.
- `get_strong_subjects()` -> DB `grades`.
- `get_weak_subjects()` -> DB `grades`.
- `get_moodle_grades(course_name)` -> Moodle grades.
- `get_moodle_courses()` -> Moodle courses.

Entry points:

- `get_ai_career_analysis(courses, cv_text, quiz_topics)`
- `run_career_agent(message, db)`

Route integration: `/api/career/analysis` enriches the AI result with job links,
job search results, and data-source metadata.

### Curriculum Agent

File: `backend/app/agents/curriculum_agent.py`

Responsibility: answer module-handbook questions.

Tools:

- `modules_by_semester(semester)` -> DB `curriculum_modules`.
- `list_all_modules()` -> DB `curriculum_modules`.
- `module_details(module_name)` -> DB `curriculum_modules`.

Entry point: `run_curriculum_agent(message, db)`.

### Other AI-Backed Services

- Email summary service: `backend/app/services/email_summary_service.py`
  uses LLM structured output to summarize fetched email.
- Job agent route: `backend/app/api/v1/job_agent.py` calls an n8n webhook; it is
  not a LangChain agent, but it is an external automation integration.

## 3. API Route Map

### Chat and Prompt

- `POST /api/prompt`
  - Body: `{prompt, chat_id?, user_id?, moodle_context?}`.
  - Response: Server-Sent Events stream.
  - Calls: `run_orchestrator`.
  - Business logic: stream answer chunks and persist chat message after success.
  - Errors: agent exception yields `[ERROR]` SSE; invalid prompt/IDs -> `422`.

- `POST /api/chat/title`
  - Body: `{question}`.
  - Response: `{title}`.
  - Calls: `ainvoke_with_model_fallback`.
  - Errors: LLM failure returns first 40 chars fallback.

- `GET /api/history`
  - Response: last 50 `ChatMessage` rows.
  - Errors: DB failure -> `503`.

### Upload and Documents

- `POST /api/upload`
  - Body: multipart file, optional `chat_id`, `user_id`.
  - Response: `{status, filename}`.
  - Calls: `process_document_sync` in background.
  - DB: inserts `documents`.
  - Filesystem: writes to `uploads/<chat_id or global>/<filename>`.
  - Validation: PDF content type, `.pdf` filename, safe scope IDs.
  - Errors: invalid file -> `400`, storage failure -> `500`.

- `GET /api/documents`
  - Query: `user_id`.
  - Response: list of indexed source names from Chroma metadata.
  - Errors: Chroma unavailable -> `[]`.

- `GET /api/documents/file?name=...`
  - Response: inline PDF file.
  - Logic: searches upload folders for newest matching safe filename.
  - Errors: invalid filename -> `400`, missing file -> `404`.

- `DELETE /api/documents?name=...`
  - Deletes DB row, Chroma chunks, and disk file.
  - Errors: DB failure -> `503`.

### Tutor and Quiz

- `POST /api/tutor/quiz/generate`
  - Body: source documents, num questions, course/chat/user metadata.
  - Calls: `services.tutor_service.generate_quiz`.
  - DB: `quizzes`, `quiz_questions`.
  - Errors: invalid input -> `422`; LLM/DB failure -> `503`.

- `GET /api/tutor/quizzes`
  - Returns saved quizzes.

- `GET /api/tutor/quiz/{quiz_id}`
  - Returns quiz with questions.
  - Errors: not found -> `404`.

- `POST /api/tutor/quiz/{quiz_id}/submit`
  - Body: answers.
  - DB: creates `quiz_attempts`, `quiz_attempt_answers`.
  - Validation: question IDs must belong to that quiz; no duplicates.
  - Errors: invalid question -> `422`, missing quiz -> `404`.

- `POST /api/tutor/quiz/{quiz_id}/review`
  - Calls `generate_quiz_review`.
  - Returns Markdown review.

- `GET /api/tutor/stats`
  - Aggregates attempt answers into weak/strong question lists.

- `DELETE /api/tutor/stats`
  - Deletes attempts and answers.

- `GET /api/tutor/profile`
  - Aggregates topic mastery by quiz/module.

- `POST /api/tutor/quiz/weakness`
  - Builds a quiz from weak topics' source documents.

### Planner and Study Advisor

- `POST /api/planner/study-plan`
  - Body: `{horizon_days}` from 1 to 21.
  - Calls: `run_planner_agent`.
  - Response: `{plan}`.
  - Errors: invalid horizon -> `422`.

- `GET /api/planner/events`
  - Returns all `academic_events` enriched with priority.

- `GET /api/planner/events/upcoming`
  - Returns future `academic_events`.

- `POST /api/ai/study-advisor`
  - Body: `{message}`.
  - Logic: deterministic Moodle questions go to Moodle context service;
    otherwise Planner Agent.
  - Errors: blank message -> `422`.

### Evaluator

- `POST /api/ai/evaluate`
  - Body: `{message}`.
  - Calls: `run_evaluator_agent`.
  - Errors: blank message -> `422`, agent failure -> `503`.

- `GET /api/ai/knowledge-gaps`
  - Calls: `get_knowledge_gap_analysis`.

### Career and Jobs

- `GET /api/career/analysis`
  - Reads grades, CV, quiz mastery, curriculum competencies.
  - Calls: `get_ai_career_analysis`, `search_jobs`, `build_job_links`.
  - External services: Gemini/Groq, Adzuna or Arbeitnow.
  - Errors: DB failure -> `503`, AI failure -> `503`.

- `GET /api/career/cv`
  - Returns whether a CV exists.

- `POST /api/career/cv`
  - Multipart PDF upload.
  - Extracts PDF text into `resumes`.
  - Errors: non-PDF -> `400`, unreadable/scanned PDF -> `422`.

- `DELETE /api/career/cv`
  - Deletes stored CV.

- `POST /api/job-agent/run`
  - Multipart CV PDF.
  - Calls `/api/career/analysis`, normalizes best match, sends file and profile
    to n8n webhook.
  - Errors: missing webhook -> `503`, n8n request/status failure -> `502`.

### Calendar and LSF

- `GET /api/calendar/events`
  - Returns all calendar events ordered by start time.

- `POST /api/calendar/events`
  - Body: title, start_time, end_time, location, description.
  - Creates a user calendar event.
  - Validation: nonblank title, end after start.

- `DELETE /api/calendar/events/{event_id}`
  - Deletes user or Moodle events, not LSF events.

- `POST /api/calendar/moodle-deadlines`
  - Gets upcoming Moodle deadlines and creates calendar events.
  - Uses deterministic `uid` to avoid duplicates.

- `DELETE /api/calendar/moodle-deadlines`
  - Removes generated Moodle deadline events.

- `GET /api/lsf/grades`, `/api/lsf/termine`, `/api/lsf/exams`, `/api/lsf/profile`
  - Mock LSF data.

- `POST /api/lsf/sync`
  - Writes mock grades, timetable, planner events, exams into DB.

### Curriculum

- `GET /api/curriculum/status`
  - Returns extraction status and module counts.

- `GET /api/curriculum`
  - Lists extracted curriculum modules.

- `POST /api/curriculum/upload`
  - Multipart PDF.
  - Extracts text and runs background LLM extraction into `curriculum_modules`.

- `POST /api/curriculum/suggest-module`
  - Body: `{documents, user_id}`.
  - Suggests module for selected documents.

- `DELETE /api/curriculum`
  - Clears module handbook data.

### Moodle

- `GET /api/moodle/status`
  - Returns whether token is configured.

- `GET /api/moodle/courses`
  - Calls Moodle `core_enrol_get_users_courses`.

- `GET /api/moodle/course/{course_id}/content`
  - Raw `core_course_get_contents`.

- `GET /api/moodle/course/{course_id}/overview`
  - Simplified sections/items for frontend.

- `GET /api/moodle/course/{course_id}/grades`
  - Uses `gradereport_user_get_grade_items`.

- `GET /api/moodle/course/{course_id}/deadlines`
  - Extracts assignment modules with due dates.

- `POST /api/moodle/index`
  - Body: `{course_name, chat_id?, user_id}`.
  - Downloads indexable files and stores chunks in Chroma.

### Profile

- `POST /api/profile/reset`
  - Clears quiz data, docs, CV, curriculum, user calendar events, Chroma
    collection, and uploaded files.
  - Leaves LSF mock data untouched.

## 4. Database Tables

- `grades`: synced LSF grades; used by Grades, Career, Planner.
- `academic_events`: assignments/exams/presentations; used by Planner.
- `calendar_events`: LSF timetable, user events, Moodle deadline events.
- `exams`: exam display.
- `documents`: uploaded file metadata.
- `chat_messages`: prompt history.
- `quizzes`, `quiz_questions`, `quiz_attempts`, `quiz_attempt_answers`:
  quiz lifecycle and mastery analysis.
- `curriculum_modules`: module handbook extraction.
- `resumes`: CV text for career analysis.

## 5. RAG System

```text
PDF upload or Moodle file download
  -> text extraction
  -> chunking
  -> Gemini embeddings
  -> ChromaDB upsert with metadata
  -> retrieval by query and metadata filter
  -> LLM prompt with retrieved context
  -> grounded answer
```

### Upload RAG Flow

1. Frontend sends `POST /api/upload`.
2. Backend saves the PDF under `uploads/<scope>`.
3. Backend inserts a `Document` row.
4. Background task calls `process_document_sync`.
5. `_extract_text` uses `pypdf`.
6. `_chunk_document_text` uses `RecursiveCharacterTextSplitter`.
7. `embed_texts` uses Gemini embeddings.
8. `get_collection` connects to ChromaDB.
9. Chunks are upserted with metadata:
   - `source`
   - `chunk`
   - `chat_id`
   - `user_id`
10. Tutor retrieves with `retrieve_context`.

### Retrieval Flow

`retrieve_context(query, source_filter, chat_id, user_id, metadata_filter)`:

1. Embed query.
2. Build Chroma `where` filter.
3. Query top-k chunks.
4. Optionally filter by distance threshold.
5. Format context as `[Quelle n - source]`.

Things that can go wrong:

- PDF has no extractable text.
- Gemini embedding fails.
- Chroma is not running.
- Metadata filters do not match stored chunks.
- User asks before background indexing is finished.

The code generally returns empty context instead of crashing, then the agent
explains that no indexed material was found.

## 6. Moodle Deep Dive

### Moodle Configuration

Settings live in `backend/app/core/config.py`:

- `MOODLE_URL`
- `MOODLE_TOKEN`
- `MOODLE_USER_ID`

`moodle_service.is_configured()` returns true only when a token exists.

### Moodle Sync vs Moodle Live Use

There is no full persistent Moodle sync table. Moodle is mostly used live:

- courses are loaded from Moodle API;
- course overview is loaded live;
- deadlines are loaded live and can be copied to `calendar_events`;
- materials are downloaded on demand and indexed into ChromaDB.

This is a lazy architecture: it avoids bulk importing every Moodle file, but it
means first answers can be slow and quality depends on matching the right file.

### Moodle File Download and Indexing

Important functions in `moodle_service.py`:

- `get_moodle_course_content(course_id)`
  - Calls `core_course_get_contents`.
  - Returns Moodle sections/modules.

- `get_moodle_course_overview(course_id)`
  - Converts raw sections into frontend-friendly `{section_name, items}`.
  - Adds tokenized `open_url` for files.

- `get_course_files(course_id)`
  - Returns indexable `.pdf`, `.pptx`, `.docx` files.

- `download_file_text(fileurl, filename)`
  - Downloads with Moodle token.
  - Extracts PDF/PPTX/DOCX text.

- `index_course_by_name(name, chat_id, user_id, max_files)`
  - Finds a course.
  - Gets files.
  - Downloads up to `max_files`.
  - Calls `rag.pipeline.index_text`.
  - Stores metadata including `moodle=1`, `course_id`, `course_name`.

### Moodle in Chat

There are two Moodle paths:

1. Deterministic context path:
   - `orchestrator.should_route_to_moodle_context`
   - `moodle_context_service.get_moodle_context_for_message`
   - Answers course lists, deadlines, grades, and material overviews without LLM
     RAG.

2. Selected Moodle material RAG path:
   - Frontend builds `moodle_context` from selected course overview.
   - `/api/prompt` passes it to Orchestrator.
   - Orchestrator/Tutor detect selected material questions.
   - Tutor finds files, indexes if needed, retrieves Chroma context, then calls
     the LLM.

### Why Moodle Result Quality Can Be Weak

The current architecture is reasonable, but quality can be weak for these
reasons:

- Lazy indexing means first use depends on successful download and extraction.
- Matching was mostly exact substring based. Labels like `Session 01` did not
  reliably match `Session 1`.
- Moodle course content often has weak filenames, many duplicate labels, or
  generic section names.
- PDF extraction can fail for scanned slides.
- PPTX text extraction loses visual context, diagrams, speaker notes, and
  layout semantics.
- The deterministic Moodle path returns metadata summaries, not full semantic
  answers.
- If no selected Moodle course context is sent from the frontend, the Tutor must
  rely on LLM tool use to choose and index a course, which is less reliable.

### Improvement Implemented

Implemented in `backend/app/agents/tutor_agent.py`:

- Added normalized Moodle matching:
  - lowercasing
  - accent removal
  - punctuation normalization
  - leading-zero normalization
  - token subset matching

Impact:

- `Session 1`, `session-1`, and `Session 01` can now match.
- File names like `usw_session_01.pptx` are easier to match from natural user
  questions.
- The change is local and safe: it only broadens matching for selected Moodle
  material and is covered by tests.

### Recommended Moodle Architecture Improvements

Not all should be done at once, but these are the best next steps:

1. Add a persistent `moodle_resources` table.
   - Store course_id, section, module, filename, fileurl hash, indexed_at,
     extraction_status, chunk_count.
   - This makes indexing visible and debuggable.

2. Add explicit "Index selected course" and "Index selected section" actions.
   - Better UX than silently indexing during chat.

3. Add OCR or image extraction for scanned PDFs/slides.
   - Current text-only extraction misses visual slide decks.

4. Store Moodle resource metadata in Chroma and DB consistently.
   - Current Chroma metadata is good, but DB has no Moodle resource ledger.

5. Improve retrieval ranking.
   - Current selected material retrieval uses `threshold=None` for broad recall.
   - A reranker or hybrid keyword+vector retrieval would improve precision.

6. Cache Moodle overviews and file lists with explicit refresh.
   - Current deadline/course cache exists, but material overview indexing is
     mostly live.

## 7. End-to-End Feature Workflows

### Prompt / Chat

```text
User message
  -> frontend sendPrompt
  -> /api/prompt SSE
  -> run_orchestrator
  -> deterministic Moodle OR supervisor agent OR Tutor direct path
  -> answer chunks streamed back
  -> chat saved to DB and localStorage
```

### Tutor

- General concept question -> direct LLM answer.
- Document/Moodle question -> RAG/tool path.
- Selected Moodle material -> direct Moodle RAG path.
- Quiz generation -> retrieve context, generate structured questions, persist.

### Planner

- Reads planner events, calendar blocks, grades, Moodle deadlines.
- Generates study plans around unavailable time.
- `/api/planner/study-plan` validates horizon 1-21 days.

### Evaluator

- Reads quiz attempts and answer correctness.
- Identifies weak questions/topics and prerequisite modules.
- Can use Moodle grades as additional context.

### Study Advisor

- Thin endpoint.
- Moodle-specific messages go to deterministic Moodle context.
- Other messages go to Planner Agent.

### Profile

- Reset deletes user-generated learning data, vector index, and uploaded files.
- Leaves LSF mock data because it can be regenerated.

### Curriculum

- User uploads module handbook PDF.
- Text extraction runs.
- Background service uses LLM to extract modules/prerequisites/competencies.
- Agents use curriculum for prerequisites and module suggestions.

### Calendar

- LSF sync writes class events.
- User can add/delete own events.
- Moodle deadlines can be copied into calendar.
- LSF events are read-only.

## 8. How to Test Moodle Integration

### Backend Tests

Run:

```bash
cd backend
pytest tests/test_moodle.py tests/test_moodle_context_service.py tests/test_tutor_routing.py
```

Expected:

- Moodle course transform tests pass.
- Deadline tests pass with frozen dates.
- Moodle PPTX download/index/explain test passes.
- Fuzzy session matching test passes.

Full validation:

```bash
cd backend
pytest
python -m compileall -q app tests
cd ../frontend
npm run build
npm audit --omit=dev
```

### Frontend Moodle Actions

1. Configure `MOODLE_TOKEN` and `MOODLE_USER_ID`.
2. Start backend and frontend.
3. Open Moodle page in the UI.
4. Load courses.
5. Select a course.
6. Open overview.
7. Click a file/material and ask for explanation.

Expected:

- Course list loads.
- Sections and items load.
- Clicking/asking about a selected file sends `moodle_context`.
- First answer may take longer because indexing can happen on demand.
- Later answers should be faster because Chroma already has chunks.

### Chat Questions to Ask

- `Welche Moodle-Kurse habe ich im 5. Semester?`
  - Expected: deterministic list of semester courses.

- `Was ist meine nächste Moodle-Aufgabe?`
  - Expected: next upcoming Moodle assignment, not LSF exam.

- `Welche Moodle-Deadlines stehen an?`
  - Expected: sorted upcoming Moodle deadlines plus calendar offer.

- `Erkläre mir die Slides aus Session 1`
  - Expected: selected Moodle RAG answer grounded in matching section/file.

- `Erkläre usw_session_01.pptx`
  - Expected: answer from that file.

- `Fasse die wichtigsten Konzepte aus diesem Moodle-Material zusammen`
  - Expected: summary, concepts, takeaways, optional quiz questions.

### Moodle Edge Cases

- Token missing: `/api/moodle/status` false; routes return `503`.
- Expired token: Moodle routes return `502` with Moodle error.
- Course has no files: indexing returns zero files.
- File is scanned PDF: extraction returns no text; answer says no readable indexed
  content.
- Course has `Session 01` but user says `Session 1`: should now match.
- User asks about Moodle deadline after deadline date: past deadline ignored for
  "next" queries.

## 9. What Changed in This Pass

- Improved Moodle material matching in `tutor_agent.py`.
- Added regression test for fuzzy Moodle session matching in
  `tests/test_tutor_routing.py`.
- Earlier hardening remains part of current workspace:
  - curriculum router registration,
  - strict API validation,
  - upload path safety,
  - profile reset clearing uploads,
  - Markdown sanitization,
  - quiz submission validation,
  - Moodle PDF extraction fix,
  - dependency manifest alignment.

## 10. Critical Assessment

The architecture is good for an MVP: FastAPI routes are separated by feature,
agents are isolated by responsibility, RAG is defensive, and Moodle is lazy so
the app does not need a large sync job before first use.

The fragile parts are:

- no real auth or multi-user ownership enforcement yet;
- no Alembic migrations;
- frontend is concentrated in one very large Vue component;
- Moodle resources have no DB ledger;
- Chroma failures are intentionally silent, which is user-friendly but hard to
  diagnose;
- file extraction is text-only and weak for scanned/visual learning material.

The best next architectural move is a Moodle resource/indexing table plus a
small UI status panel showing which Moodle files are indexed, failed, or stale.
