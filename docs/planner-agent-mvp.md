# Planner Agent MVP — Technical Documentation

**Project:** Adaptive Study & Career Agent (GenAI-USW-2026)
**Module:** Unternehmenssoftware, 5th Semester
**Implementation Date:** June 2026
**Status:** MVP Complete

---

## 1. Feature Name

**Planner Agent MVP — Academic Event Management with Priority Calculation**

---

## 2. Objective

Students at university face a recurring challenge: managing multiple overlapping deadlines across different courses — exams, assignment submissions, and presentations — without a structured tool to prioritize their workload.

The Planner Agent MVP solves this by providing a dedicated module where students can manually register upcoming academic events and immediately receive a calculated priority level based on how much time remains until the deadline. This gives students a clear, sorted view of what requires their attention most urgently.

The MVP deliberately focuses on **future event management only**. Past grades and academic history are intentionally excluded — these will be handled separately in a later phase for weakness analysis. This separation of concerns keeps the planner focused on actionable, forward-looking information.

The implementation also lays the architectural groundwork for a future AI-powered Planner Agent that will consume these events to generate study plans, learning goals, and deadline alerts automatically.

---

## 3. User Story

> **As a student**, I want to manually add upcoming exams, assignments, and presentations to a planner, so that I can see all my academic deadlines in one place, sorted by urgency, and understand which events require my immediate attention.

**Acceptance Criteria:**

- I can add an event with a title, course name, type, date, and optional description.
- The system tells me how many days remain until each event.
- Each event is automatically labeled as URGENT, HIGH, or NORMAL priority.
- Events are displayed sorted by nearest date.
- I can remove an event once it is no longer relevant.
- The planner is always accessible from the navigation bar.

---

## 4. Functional Overview

The Planner feature provides the following capabilities:

| Capability | Description |
|---|---|
| Add Event | Student fills out a form with title, course name, event type, date, and optional description |
| View All Events | All stored events are displayed sorted by nearest date first |
| View Upcoming Events | A dedicated API endpoint filters out past events and returns only future ones |
| Priority Display | Each event card shows days remaining and a color-coded priority badge (URGENT / HIGH / NORMAL) |
| Type Classification | Events are classified as EXAM, ASSIGNMENT, or PRESENTATION with distinct visual badges |
| Delete Event | Any event can be removed with a single click; the list updates immediately without a page reload |
| Persistent Storage | Events are saved in a PostgreSQL database and survive server restarts |
| Auto-load | The planner loads existing events automatically when the application starts |

---

## 5. Technical Implementation

### 5.1 Frontend Changes

**File modified:** `frontend/src/App.vue`

The entire frontend is a single-page Vue 3 application contained in `App.vue`. The planner was integrated directly into this file following the same pattern used by the existing Calendar and Grades panels.

**Changes made:**

**a) New navigation item** added to the `navItems` array in `data()`:
```javascript
{
  id: 'planner',
  label: 'Planner',
  icon: '📋',
  entries: []
}
```
This registers the "📋 Planner" button in the top navigation bar.

**b) Dropdown width class** updated to include the planner panel:
```html
:class="['dropdown', {
  'dropdown--wide': item.id === 'kalender',
  'dropdown--extra-wide': item.id === 'noten' || item.id === 'planner'
}]"
```
The planner uses the `dropdown--extra-wide` class (560px min-width) to accommodate the input form and event list side by side.

**c) Planner template section** added inside the dropdown (`v-if="item.id === 'planner'"`), containing:
- An HTML `<form>` with five input fields and a submit button
- A status message paragraph for success/error feedback
- A conditional event list rendered with `v-for`

**d) New reactive data properties** added:
```javascript
plannerEvents: [],          // Holds the list fetched from the API
plannerSubmitting: false,   // Disables the submit button during POST
plannerStatus: null,        // Displays success/error messages
plannerForm: {              // Bound to the form inputs
  title: '',
  course_name: '',
  type: 'EXAM',             // Default selection
  date: '',
  description: ''
}
```

**e) New methods** added:

| Method | Purpose |
|---|---|
| `fetchPlannerEvents()` | `GET /api/planner/events` on mount and after every create |
| `submitPlannerEvent()` | Validates form locally, `POST`s to API, resets form on success |
| `deletePlannerEvent(id)` | `DELETE /api/planner/events/{id}`, removes item from local array without a full reload |
| `plannerTypeLabel(type)` | Maps `EXAM` → `Prüfung`, `ASSIGNMENT` → `Abgabe`, `PRESENTATION` → `Präsentation` |
| `formatPlannerDate(dateStr)` | Formats ISO date string to German locale (DD.MM.YYYY) |

**f) `mounted()` hook** extended to call `fetchPlannerEvents()` alongside the existing `fetchCalendarEvents()`.

**g) CSS styles** appended at the end of the `<style>` block — 17 new CSS classes covering the planner section, form inputs, event cards, type badges, and priority badges.

---

### 5.2 Backend Changes

**File modified:** `backend/app/main.py`

Two changes:
1. Import added: `from app.api.v1 import ..., planner, ...`
2. Router registered: `app.include_router(planner.router, prefix="/api")`

**File modified:** `backend/app/models/__init__.py`

Added import and export of the new model:
```python
from app.models.academic_event import AcademicEvent
```
This is required so that `Base.metadata.create_all()` discovers and creates the `academic_events` table on startup.

---

### 5.3 Database Changes

**New table created automatically on application startup:** `academic_events`

The table is created by SQLAlchemy's `Base.metadata.create_all()` call in the application lifespan handler in `main.py`. No manual migration is needed.

A new PostgreSQL **ENUM type** named `academic_event_type` is also created automatically with three allowed values: `EXAM`, `ASSIGNMENT`, `PRESENTATION`.

---

### 5.4 New Model

**File created:** `backend/app/models/academic_event.py`

Defines the `AcademicEvent` SQLAlchemy ORM class mapped to the `academic_events` table. Uses SQLAlchemy 2.0 mapped column syntax with Python type annotations (`Mapped[T]`), consistent with all other models in the project.

---

### 5.5 New Service

**Files created:**
- `backend/app/services/__init__.py` (empty package marker)
- `backend/app/services/planner_service.py`

The `planner_service.py` module contains a single pure function `get_event_priority(event_date: date) -> dict`. It is intentionally stateless and has no database dependency, making it independently testable and reusable. The function returns a dictionary with two keys: `days_remaining` (integer, minimum 0) and `priority` (string).

---

### 5.6 New API Router

**File created:** `backend/app/api/v1/planner.py`

Implements four REST endpoints using FastAPI's `APIRouter`. Each endpoint uses SQLAlchemy's async session via dependency injection (`Depends(get_db)`). All database exceptions are caught and converted to `503 Service Unavailable` to protect against unhandled crashes.

---

## 6. Workflow

### Creating an Event

```
Student
  │
  ▼
Opens "📋 Planner" in navigation bar
  │
  ▼
Fills form: title, course name, type, date, description
  │
  ▼
Clicks "+ Event hinzufügen"
  │
  ▼
Frontend: submitPlannerEvent()
  │  Local validation (title, course_name, date required)
  │
  ▼
POST /api/planner/events
  │  JSON body sent with Content-Type: application/json
  │
  ▼
Backend: create_event()
  │  Type validation against VALID_TYPES set
  │  Whitespace stripped from title and course_name
  │
  ▼
Database: INSERT INTO academic_events (...)
  │  Row committed, refreshed with generated id and created_at
  │
  ▼
Planner Service: get_event_priority(event.date)
  │  Calculates days_remaining and priority
  │
  ▼
API Response: 201 Created
  │  Full AcademicEventOut JSON including days_remaining + priority
  │
  ▼
Frontend: form reset, fetchPlannerEvents() called
  │
  ▼
GET /api/planner/events → updated list returned
  │
  ▼
plannerEvents array updated → Vue re-renders list
  │
  ▼
Status message "Event gespeichert!" shown for 3 seconds
```

### Deleting an Event

```
Student clicks ✕ on event card
  │
  ▼
Frontend: deletePlannerEvent(id)
  │
  ▼
DELETE /api/planner/events/{id}
  │
  ▼
Backend: verifies event exists, deletes row, commits
  │
  ▼
204 No Content
  │
  ▼
Frontend: plannerEvents.filter(e => e.id !== id)
  │  Local array updated without a full API reload
  │
  ▼
Vue re-renders event list (removed item disappears)
```

### Application Startup

```
Vue mounted() hook fires
  │
  ├── fetchCalendarEvents()  → GET /api/calendar/events
  └── fetchPlannerEvents()   → GET /api/planner/events
        │
        ▼
        plannerEvents array populated
        │
        ▼
        Planner panel ready with existing events pre-loaded
```

---

## 7. Data Structure

### Database Table: `academic_events`

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | `INTEGER` | Primary Key, Auto-increment | Unique identifier for each event |
| `user_id` | `VARCHAR(255)` | Nullable | Reserved for future multi-user authentication |
| `title` | `VARCHAR(255)` | NOT NULL | Name of the event (e.g., "Datenbanken Klausur") |
| `course_name` | `VARCHAR(255)` | NOT NULL | Name of the associated course (e.g., "Datenbanken") |
| `type` | `ENUM` | NOT NULL | One of: `EXAM`, `ASSIGNMENT`, `PRESENTATION` |
| `date` | `DATE` | NOT NULL | The date of the event (date only, no time component) |
| `description` | `TEXT` | Nullable | Optional free-text notes |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | NOT NULL, auto-set | UTC timestamp of when the record was created |

### Computed Fields (not stored in DB)

| Field | Type | Calculated By | Purpose |
|---|---|---|---|
| `days_remaining` | `INTEGER` | `planner_service.get_event_priority()` | Number of days from today to event date (min 0) |
| `priority` | `STRING` | `planner_service.get_event_priority()` | `URGENT`, `HIGH`, or `NORMAL` |

### Priority Thresholds

| Condition | Priority Label | UI Color |
|---|---|---|
| `days_remaining <= 7` | `URGENT` | Red badge |
| `days_remaining <= 14` | `HIGH` | Amber badge |
| `days_remaining > 14` | `NORMAL` | Green badge |

### Frontend Form State Object: `plannerForm`

| Key | Default | Bound To |
|---|---|---|
| `title` | `''` | Text input |
| `course_name` | `''` | Text input |
| `type` | `'EXAM'` | `<select>` dropdown |
| `date` | `''` | `<input type="date">` |
| `description` | `''` | Text input (optional) |

---

## 8. API Documentation

### 8.1 Create Academic Event

| | |
|---|---|
| **Method** | `POST` |
| **URL** | `/api/planner/events` |
| **Status on success** | `201 Created` |

**Request Body (JSON):**
```json
{
  "title": "Datenbanken Klausur",
  "course_name": "Datenbanken",
  "type": "EXAM",
  "date": "2026-07-20",
  "description": "SQL, Normalisierung, Transaktionen"
}
```

| Field | Required | Type | Validation |
|---|---|---|---|
| `title` | Yes | string | Whitespace stripped |
| `course_name` | Yes | string | Whitespace stripped |
| `type` | Yes | string | Must be `EXAM`, `ASSIGNMENT`, or `PRESENTATION` |
| `date` | Yes | date (`YYYY-MM-DD`) | ISO 8601 date format |
| `description` | No | string or null | Optional free text |

**Response Body (JSON):**
```json
{
  "id": 1,
  "title": "Datenbanken Klausur",
  "course_name": "Datenbanken",
  "type": "EXAM",
  "date": "2026-07-20",
  "description": "SQL, Normalisierung, Transaktionen",
  "created_at": "2026-06-09T14:23:00.000000Z",
  "days_remaining": 41,
  "priority": "NORMAL"
}
```

**Error Responses:**

| Status | Reason |
|---|---|
| `422 Unprocessable Entity` | Invalid `type` value or missing required fields |
| `503 Service Unavailable` | PostgreSQL not reachable |

---

### 8.2 Get All Events

| | |
|---|---|
| **Method** | `GET` |
| **URL** | `/api/planner/events` |
| **Status on success** | `200 OK` |
| **Sorting** | Ascending by `date` (nearest first) |

**Request Body:** None

**Response Body (JSON array):**
```json
[
  {
    "id": 3,
    "title": "Präsentation Softwareprojekt",
    "course_name": "Unternehmenssoftware",
    "type": "PRESENTATION",
    "date": "2026-06-15",
    "description": null,
    "created_at": "2026-06-09T10:00:00.000000Z",
    "days_remaining": 6,
    "priority": "URGENT"
  },
  {
    "id": 1,
    "title": "Datenbanken Klausur",
    "course_name": "Datenbanken",
    "type": "EXAM",
    "date": "2026-07-20",
    "description": "SQL, Normalisierung, Transaktionen",
    "created_at": "2026-06-09T14:23:00.000000Z",
    "days_remaining": 41,
    "priority": "NORMAL"
  }
]
```

Returns all events including past ones. Each item includes computed `days_remaining` and `priority`.

---

### 8.3 Get Upcoming Events

| | |
|---|---|
| **Method** | `GET` |
| **URL** | `/api/planner/events/upcoming` |
| **Status on success** | `200 OK` |
| **Filter** | Only events where `date >= today` |
| **Sorting** | Ascending by `date` (nearest first) |

**Request Body:** None

**Response Body:** Same schema as **8.2**, but excludes any events whose date is in the past.

This endpoint is designed as the primary data source for the future AI Planner Agent, which will consume only active deadlines.

---

### 8.4 Delete Event

| | |
|---|---|
| **Method** | `DELETE` |
| **URL** | `/api/planner/events/{event_id}` |
| **URL Parameter** | `event_id` — integer, the `id` of the event to delete |
| **Status on success** | `204 No Content` |

**Request Body:** None

**Response Body:** None (empty body on success)

**Error Responses:**

| Status | Reason |
|---|---|
| `404 Not Found` | No event with the given `id` exists |
| `503 Service Unavailable` | PostgreSQL not reachable |

---

## 9. Example Usage

### Example 1: Student adds an urgent exam

A student realizes their database exam is in 5 days. They open the Planner panel and fill in:

- **Title:** Datenbanken Klausur
- **Course Name:** Datenbanken
- **Type:** Prüfung (EXAM)
- **Date:** 14.06.2026
- **Description:** Kapitel 4–7, SQL JOINs

After clicking "+ Event hinzufügen", the API responds with:
```json
{
  "id": 7,
  "title": "Datenbanken Klausur",
  "course_name": "Datenbanken",
  "type": "EXAM",
  "date": "2026-06-14",
  "days_remaining": 5,
  "priority": "URGENT"
}
```

The event card immediately appears in the list displaying:
```
Datenbanken Klausur                          [Prüfung]
Datenbanken
📅 14.06.2026    5 Tage verbleibend    [URGENT]
```
The URGENT badge is rendered in red.

---

### Example 2: Student adds a presentation two weeks away

- **Title:** Projektpräsentation GenAI
- **Course Name:** Unternehmenssoftware
- **Type:** Präsentation (PRESENTATION)
- **Date:** 23.06.2026

API response: `days_remaining: 14`, `priority: "HIGH"`

The event card shows:
```
Projektpräsentation GenAI                    [Präsentation]
Unternehmenssoftware
📅 23.06.2026    14 Tage verbleibend    [HIGH]
```
The HIGH badge is rendered in amber.

---

### Example 3: Calling the upcoming endpoint (for future AI Agent)

A future AI agent can call `GET /api/planner/events/upcoming` and receive only future events with pre-calculated priorities, ready to generate a study schedule:

```json
[
  {
    "title": "Datenbanken Klausur",
    "type": "EXAM",
    "date": "2026-06-14",
    "days_remaining": 5,
    "priority": "URGENT"
  },
  {
    "title": "Projektpräsentation GenAI",
    "type": "PRESENTATION",
    "date": "2026-06-23",
    "days_remaining": 14,
    "priority": "HIGH"
  }
]
```

---

## 10. Future Improvements

The MVP was designed with intentional extension points. The following improvements are planned for future project phases:

### Phase 2: AI-Powered Study Plans

The `GET /api/planner/events/upcoming` endpoint exists specifically to feed a Gemini-powered Planner Agent. In the next phase, this agent will:
- Consume upcoming events sorted by priority
- Generate a week-by-week study plan as a structured text output
- Suggest daily learning goals per course
- Deliver deadline alerts ("You have 2 days left for X")

The service layer (`planner_service.py`) is already isolated as the entry point for this logic expansion.

### Phase 3: Weakness-Aware Planning

Once the grade extraction feature (Noten) is fully integrated, the Planner Agent will be able to cross-reference a student's past performance (weak subjects) with upcoming events and allocate more study time to courses where the student historically struggled.

### Phase 4: User Authentication

The `user_id` column in `academic_events` is already present but currently not populated (`NULL`). Once JWT-based authentication is added, this field will scope events to individual users, enabling multi-user support.

### Phase 5: Notifications and Reminders

The priority system could drive scheduled notifications (e.g., via n8n webhooks or email) when an event transitions from NORMAL → HIGH or HIGH → URGENT.

### Additional Technical Improvements

| Improvement | Rationale |
|---|---|
| Add `PUT /api/planner/events/{id}` for editing | Students may need to change a date or description |
| Pagination on `GET /api/planner/events` | The list will grow over a full semester |
| Frontend search/filter | Useful once students have many events across multiple courses |
| Unit tests for `planner_service.py` | The pure function is already well-suited for isolated pytest coverage |

---

## 11. How to Present This Feature

### What the Audience Should Understand

1. **The problem is real.** University students manage multiple overlapping deadlines across several courses simultaneously. A tool that centralizes and prioritizes this information has direct practical value.

2. **The MVP scope is intentional.** The planner focuses exclusively on future events. It does not touch grades, past performance, or AI generation yet — because those are more complex problems that build on top of a working event management foundation.

3. **The architecture is future-proof.** Every design decision — the dedicated service layer, the `user_id` placeholder, the `/upcoming` endpoint — was made to support the AI agent that will be built on top of this.

### Key Points to Explain

- **Priority calculation is automatic.** The student only enters the date; the system computes whether the event is URGENT, HIGH, or NORMAL based on a clear, understandable rule set. There is no ambiguity.

- **The data is persistent.** Events survive server restarts because they are stored in PostgreSQL, not just in browser memory.

- **The frontend integrates seamlessly.** The planner uses the exact same navigation, styling system, and CSS variables as the rest of the application. It feels like a natural part of the product, not an add-on.

- **The service layer is the AI-ready interface.** Show the `planner_service.py` file: it is a pure function that takes a date and returns priority metadata. This is exactly what a LangChain tool or Gemini function call would invoke.

### Live Demo Script

1. Open the application at `http://localhost:5173`
2. Click "📋 Planner" in the navigation bar
3. Add an exam that is 5 days away → show the red **URGENT** badge
4. Add a presentation 10 days away → show the amber **HIGH** badge
5. Add an assignment 30 days away → show the green **NORMAL** badge
6. Show that events are sorted nearest-first automatically
7. Delete one event → show the list updates instantly
8. Open the browser DevTools Network tab → show the API call to `/api/planner/events`
9. Open `http://localhost:8080/docs` → show the FastAPI Swagger UI with all four endpoints documented

### Why This Feature Is Valuable

- It is the **foundation** for everything the Planner Agent will become. Without structured event data, there is nothing for an AI agent to plan around.
- It demonstrates **full-stack integration**: a Vue 3 form → a FastAPI REST API → SQLAlchemy async ORM → PostgreSQL → computed business logic → dynamic UI update.
- It shows **design thinking**: the decision to separate the planner from grades, the pre-built `user_id` field for future auth, the dedicated `/upcoming` endpoint for the AI agent — these are engineering decisions made for long-term quality.

---

## 12. Summary

The Planner Agent MVP delivers a complete, production-ready academic event management feature built across all layers of the application stack.

**Five new files were created:**
- `backend/app/models/academic_event.py` — ORM model and database table definition
- `backend/app/services/__init__.py` — Python package marker for the new service layer
- `backend/app/services/planner_service.py` — Pure priority calculation function
- `backend/app/api/v1/planner.py` — Four REST endpoints with async database access
- `docs/planner-agent-mvp.md` — This documentation file

**Two existing files were modified:**
- `backend/app/main.py` — Planner router imported and registered
- `backend/app/models/__init__.py` — AcademicEvent exported for table auto-creation
- `frontend/src/App.vue` — Planner nav item, panel template, reactive data, methods, and CSS added

The feature is fully functional end-to-end: students can add, view, and delete academic events through the web interface, with automatic priority calculation and persistent storage. The architecture is explicitly designed to serve as the data foundation for an AI-powered Planner Agent in the next development phase.
