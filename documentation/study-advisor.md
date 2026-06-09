# AI Study Advisor — Technical Documentation

**Project:** Adaptive Study & Career Agent (GenAI-USW-2026)
**Module:** Unternehmenssoftware, 5th Semester
**Implementation Date:** June 2026
**Status:** MVP Complete — Integrated with existing chat

---

## 1. Feature Name

**AI Study Advisor — Planner-Aware Chat Integration powered by Gemini**

---

## 2. Objective

Students who have already added their upcoming academic events (exams, assignments, presentations) to the Planner need actionable guidance: what to study today, which deadline is most urgent, how to distribute their time across multiple courses this week.

The AI Study Advisor connects the existing Planner data directly to Google Gemini. When a student types a planning-related question into the main chat — such as "What should I focus on this week?" — the system automatically fetches their real upcoming events from the database, builds a structured context, and asks Gemini to generate a personalized study recommendation.

**Key design constraint:** The feature must not break any existing functionality. The existing general-purpose AI chat (RAG-based, streaming) must continue to work exactly as before for all non-planner questions. Only questions that match a set of planner-related keywords are redirected to the Study Advisor.

---

## 3. User Story

> **As a student**, I want to ask the AI chat "What should I focus on this week?" and receive a personalized study plan based on my actual upcoming exams, assignments, and presentations — without having to copy my deadlines manually into the chat.

**Acceptance Criteria:**

- Planner-related questions in the chat automatically receive Study Advisor answers.
- The Study Advisor uses only real events stored in the database — it invents nothing.
- If no events exist, the AI tells the student to add events in the Planner first.
- Non-planner questions still use the original streaming RAG chat without any change.
- The Gemini answer is rendered with full markdown support in the chat bubble.
- A Gemini failure returns a user-friendly fallback message, not a crash.

---

## 4. Functional Overview

| Capability | Description |
|---|---|
| Planner-aware answers | AI reads real upcoming events from the DB before answering |
| Automatic keyword routing | The frontend detects planner keywords and routes to the Study Advisor silently |
| Priority-ordered context | Events are fetched sorted by nearest date; priority is recalculated via the existing planner service |
| System-prompted AI | Gemini operates under a strict system prompt that prevents event invention and enforces student-friendly formatting |
| No-event fallback | If the student has no upcoming events, the AI responds with a message to add events first |
| Error fallback | If Gemini is unavailable, a clear message is shown instead of an exception |
| Existing chat preserved | All non-planner questions continue to use the original streaming RAG chat unchanged |

---

## 5. Technical Implementation

### 5.1 Backend — New Service

**File created:** `backend/app/services/study_advisor_service.py`

This is the core logic file. It does three things in sequence:

**Step 1 — Fetch upcoming events from PostgreSQL:**
```python
result = await db.execute(
    select(AcademicEvent)
    .where(AcademicEvent.date >= today)
    .order_by(AcademicEvent.date)
)
events = result.scalars().all()
```
It queries only future events (`date >= today`), ordered nearest-first. It reuses the existing `AcademicEvent` model directly — no duplicate table or model.

**Step 2 — Build the context string:**
```python
def _build_events_context(events):
    lines = []
    for e in events:
        p = get_event_priority(e.date)   # reuses existing planner_service
        line = (
            f"- Title: {e.title} | Course: {e.course_name} | Type: {e.type} "
            f"| Date: {e.date} | Days remaining: {p['days_remaining']} | Priority: {p['priority']}"
        )
        if e.description:
            line += f" | Notes: {e.description}"
        lines.append(line)
    return "\n".join(lines)
```
Each event is formatted as a single pipe-delimited line. Priority and days remaining are recalculated using the existing `get_event_priority()` function from `planner_service.py` — not duplicated.

**Step 3 — Call Gemini with system prompt:**
```python
response = await _client.aio.models.generate_content(
    model="gemini-3.1-flash-lite-preview",
    contents=full_prompt,
    config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
)
return response.text
```
The call is non-streaming (unlike the general chat) because the Study Advisor returns a complete JSON response. The same `gemini-3.1-flash-lite-preview` model and the same `genai.Client` pattern from `prompt.py` are reused.

**Fallback handling:**
- If no events exist → returns a fixed message asking the student to add events first.
- If Gemini throws any exception → returns a fixed fallback string. The endpoint never raises an HTTP 500.

---

### 5.2 Backend — New API Router

**File created:** `backend/app/api/v1/study_advisor.py`

A minimal FastAPI router with one endpoint. Follows the exact same pattern as all other routers in the project.

```python
@router.post("/ai/study-advisor", response_model=StudyAdvisorResponse)
async def study_advisor(body: StudyAdvisorRequest, db: AsyncSession = Depends(get_db)):
    answer = await get_study_advice(body.message, db)
    return {"answer": answer}
```

The router accepts the student's question, passes it along with the async DB session to the service, and returns the result. All Gemini and database logic is inside the service — the router itself stays thin.

---

### 5.3 Backend — main.py Updated

**File modified:** `backend/app/main.py`

Two additions:
```python
# Import line updated:
from app.api.v1 import ..., study_advisor, ...

# Router registration added:
app.include_router(study_advisor.router, prefix="/api")
```

No other changes. All existing routers remain registered in their original order.

---

### 5.4 Frontend — Keyword Detection and Routing

**File modified:** `frontend/src/App.vue`

The `sendPrompt()` method was extended. The original streaming chat code is completely untouched and still runs for all non-planner questions.

**New helper method added** (`isPlannerQuestion`):
```javascript
isPlannerQuestion(text) {
  const keywords = [
    'focus', 'priority', 'deadline', 'study plan', 'this week', 'today',
    'exam', 'assignment', 'presentation', 'planner', 'urgent', 'schedule',
    'what should i', 'am i at risk', 'risk', 'prepare', 'review'
  ]
  const lower = text.toLowerCase()
  return keywords.some(kw => lower.includes(kw))
},
```
Case-insensitive. Returns `true` if any keyword appears anywhere in the message.

**Study Advisor routing block** inserted at the top of `sendPrompt()`, before the existing streaming logic:
```javascript
if (this.isPlannerQuestion(userPrompt)) {
  try {
    const res = await fetch('/api/ai/study-advisor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: userPrompt })
    })
    if (res.ok) {
      const data = await res.json()
      this.messages[this.messages.length - 1].content = data.answer
    } else {
      this.messages[this.messages.length - 1].content =
        'The Study Advisor could not process your request. Please try again.'
    }
  } catch {
    this.messages[this.messages.length - 1].content = 'Fehler: Backend nicht erreichbar.'
  } finally {
    this.loading = false
  }
  return  // ← exits sendPrompt early; streaming block below never runs
}
```
The `return` statement after the Study Advisor block ensures the original streaming fetch is never called for planner questions. If the keyword check returns `false`, execution falls through to the original code unchanged.

The response is set directly into `this.messages[last].content`. Because the chat already renders all assistant bubbles through `renderMarkdown()`, the Gemini markdown output (headings, bullets) is rendered automatically with no additional code.

---

## 6. Workflow

### Study Advisor Question Flow

```
Student types: "What should I focus on this week?"
  │
  ▼
sendPrompt() fires
  │
  ▼
isPlannerQuestion("What should I focus on this week?")
  │  keyword "this week" matched → returns true
  │
  ▼
POST /api/ai/study-advisor
  │  body: { "message": "What should I focus on this week?" }
  │
  ▼
study_advisor() route handler
  │  injects AsyncSession via Depends(get_db)
  │
  ▼
get_study_advice(message, db)
  │
  ├── SELECT * FROM academic_events WHERE date >= today ORDER BY date
  │
  ├── _build_events_context(events)
  │     → reuses get_event_priority() from planner_service
  │
  ├── Builds full_prompt:
  │     "Student's upcoming academic events:\n[event list]\n\nStudent question: ..."
  │
  └── client.aio.models.generate_content(
          model="gemini-3.1-flash-lite-preview",
          contents=full_prompt,
          config=GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
      )
  │
  ▼
Gemini API generates structured study recommendation
  │
  ▼
{ "answer": "Your top priority this week is..." }
  │
  ▼
Frontend: messages[last].content = data.answer
  │
  ▼
Vue re-renders → renderMarkdown() formats the response
  │
  ▼
Student sees formatted markdown recommendation in chat bubble
```

### Non-Planner Question Flow (Unchanged)

```
Student types: "Explain database normalization"
  │
  ▼
isPlannerQuestion(...) → false (no keywords matched)
  │
  ▼
[Study Advisor block skipped entirely]
  │
  ▼
POST /api/prompt  (original streaming RAG chat)
  │
  ▼
[Existing SSE streaming behavior — unchanged]
```

### No Events Case

```
Student types: "What should I study today?"
  │
  ▼
isPlannerQuestion → true → POST /api/ai/study-advisor
  │
  ▼
get_study_advice queries DB → empty result
  │
  ▼
Returns: "You have no upcoming academic events in your Planner yet.
          Please add your exams, assignments, and presentations in the
          Planner tab first, and I will help you prioritize them."
  │
  ▼
Message shown in chat bubble
```

---

## 7. Data Flow and Context Structure

### What Gets Sent to Gemini

The complete `contents` field sent to Gemini has this format:

```
Student's upcoming academic events:
- Title: Datenbanken Klausur | Course: Datenbanken | Type: EXAM | Date: 2026-06-14 | Days remaining: 5 | Priority: URGENT | Notes: Kapitel 4-7, SQL JOINs
- Title: WebTech Abgabe | Course: Web Technologies | Type: ASSIGNMENT | Date: 2026-06-20 | Days remaining: 11 | Priority: HIGH
- Title: Softwareprojekt Präsentation | Course: Unternehmenssoftware | Type: PRESENTATION | Date: 2026-07-01 | Days remaining: 22 | Priority: NORMAL

Student question: What should I focus on this week?
```

This structured format gives Gemini all the information it needs while being easy to parse. Priority and days remaining are recalculated at request time using `planner_service.get_event_priority()`, so they always reflect the current date.

### System Prompt Summary

The Gemini system prompt enforces the following behaviors:

| Rule | Enforcement |
|---|---|
| No event invention | "Do not invent events, deadlines, exams, or grades" |
| Use only provided data | "Use only the events provided in the context" |
| URGENT first | Explicit ordering by priority |
| Short, student-friendly | "Keep the answer short, clear, and student-friendly" |
| Structured output | "Use clear headings, short bullet points" |
| Contextual routing | Different behavior for "today", "this week", "risk" questions |
| Percentage distribution | When multiple deadlines clash, recommend workload split |

---

## 8. API Documentation

### POST /api/ai/study-advisor

| | |
|---|---|
| **Method** | `POST` |
| **URL** | `/api/ai/study-advisor` |
| **Content-Type** | `application/json` |
| **Status on success** | `200 OK` |
| **Auth required** | No (MVP — future user scoping via `user_id`) |

**Request Body:**
```json
{
  "message": "What should I focus on this week?"
}
```

| Field | Required | Type | Description |
|---|---|---|---|
| `message` | Yes | string | The student's natural-language question |

**Response Body:**
```json
{
  "answer": "## Your Study Priorities This Week\n\n**URGENT — Act now:**\n- **Datenbanken Klausur** is due in 5 days..."
}
```

| Field | Type | Description |
|---|---|---|
| `answer` | string | Gemini's markdown-formatted study recommendation |

**Error Cases (all return 200 with a user-friendly answer string, not HTTP error codes):**

| Situation | answer field content |
|---|---|
| No upcoming events in DB | "You have no upcoming academic events in your Planner yet..." |
| Gemini API failure | "The Study Advisor is temporarily unavailable. Please try again later." |

The endpoint deliberately returns `200 OK` even in error cases — the `answer` field contains the human-readable message. This prevents the frontend from needing error-specific handling logic.

---

## 9. Example Interactions

### Example 1: "What should I focus on this week?"

**DB state:** 3 events (EXAM in 5 days URGENT, ASSIGNMENT in 11 days HIGH, PRESENTATION in 22 days NORMAL)

**Gemini response:**
```
## Your Study Priorities This Week

**URGENT — Act now:**
- **Datenbanken Klausur** (Exam) is due in **5 days**.
  Focus heavily here — review Kapitel 4–7 and SQL JOINs.

**HIGH — Plan time this week:**
- **WebTech Abgabe** (Assignment) is due in 11 days.
  Reserve time in the second half of the week.

**NORMAL — Light preparation:**
- **Softwareprojekt Präsentation** is 22 days away.
  No urgent action needed, but don't ignore it.

**Suggested focus split:**
- 50% Datenbanken Klausur
- 35% WebTech Abgabe
- 15% Softwareprojekt Präsentation

**Today:** Review 2 SQL JOIN types. Practice one query.
```

---

### Example 2: "What should I do today?"

**Gemini response:**
```
## Today's Tasks

Your most urgent deadline is **Datenbanken Klausur** in 5 days. Focus here.

1. Review SQL JOIN types (INNER, LEFT, RIGHT)
2. Practice writing 3 normalization examples
3. Scan Kapitel 4 lecture notes
```

---

### Example 3: "Am I at risk of missing a deadline?"

**Gemini response:**
```
## Deadline Risk Assessment

**High risk:**
- **Datenbanken Klausur** — 5 days remaining (URGENT)
  This is the most at-risk deadline. If you have not started reviewing, begin immediately.

**Moderate risk:**
- **WebTech Abgabe** — 11 days remaining (HIGH)
  Manageable if you dedicate 2–3 hours daily after the exam.

**Low risk:**
- **Softwareprojekt Präsentation** — 22 days remaining (NORMAL)

**Recommendation:** Prioritize the Datenbanken exam now.
```

---

### Example 4: No events in DB

**Student types:** "What should I study today?"

**Chat response:**
```
You have no upcoming academic events in your Planner yet. Please add your exams,
assignments, and presentations in the Planner tab first, and I will help you
prioritize them.
```

---

### Example 5: Non-planner question (routing untouched)

**Student types:** "Explain database normalization"

No keyword matched → `isPlannerQuestion` returns `false` → the Study Advisor is never called → the original RAG streaming chat handles the question exactly as before.

---

## 10. Keyword Detection Reference

The `isPlannerQuestion()` method in `App.vue` uses the following keyword list (all matched case-insensitively, substring match):

| Keyword | Example match |
|---|---|
| `focus` | "What should I focus on?" |
| `priority` | "What is my priority?" |
| `deadline` | "Am I missing a deadline?" |
| `study plan` | "Create a study plan" |
| `this week` | "Plan my week" |
| `today` | "What should I do today?" |
| `exam` | "I have an exam coming" |
| `assignment` | "My assignment is due soon" |
| `presentation` | "How to prepare my presentation" |
| `planner` | "Check my planner" |
| `urgent` | "What is urgent?" |
| `schedule` | "Help me schedule my study" |
| `what should i` | "What should I do?" |
| `am i at risk` | "Am I at risk?" |
| `risk` | "Which deadline is most risky?" |
| `prepare` | "How should I prepare?" |
| `review` | "What should I review?" |

---

## 11. Files Created and Modified

### Files Created (3 new files)

| File | Role |
|---|---|
| `backend/app/services/study_advisor_service.py` | Core logic: fetches events, builds Gemini context, calls Gemini API, returns recommendation string |
| `backend/app/api/v1/study_advisor.py` | FastAPI router with the single `POST /api/ai/study-advisor` endpoint |
| `documentation/study-advisor.md` | This documentation file |

### Files Modified (2 existing files)

| File | Change |
|---|---|
| `backend/app/main.py` | `study_advisor` imported and router registered with `prefix="/api"` |
| `frontend/src/App.vue` | `isPlannerQuestion()` method added; `sendPrompt()` extended with keyword routing block before existing streaming code |

### Files NOT Modified (by design)

| File | Reason |
|---|---|
| `backend/app/models/academic_event.py` | Reused as-is — no duplicate model needed |
| `backend/app/services/planner_service.py` | Reused `get_event_priority()` directly — no duplication |
| `backend/app/api/v1/prompt.py` | Original streaming chat completely untouched |
| `backend/app/api/v1/planner.py` | No changes needed |
| All other routers | Untouched |

---

## 12. Architecture Decisions

### Why Non-Streaming for Study Advisor?

The existing general chat uses Server-Sent Events (SSE) streaming because it shows the user the response being "typed out" in real time. The Study Advisor uses a standard JSON response instead because:

1. The response is structured (headings, bullets) and benefits from being displayed all at once after markdown rendering.
2. It simplifies the service code — no streaming generator, no SSE framing.
3. A typical Study Advisor response is short (under 300 words), so the wait time is negligible.

The streaming code in `sendPrompt()` was not modified — the Study Advisor path returns before it is reached.

### Why Keyword Detection in the Frontend?

Routing is done in the frontend rather than the backend for two reasons:

1. **No additional API call overhead** — the routing decision is instant and local.
2. **The backend stays clean** — the two endpoints (`/api/prompt` and `/api/ai/study-advisor`) remain independent and testable in isolation.

A backend-side router would require the general prompt endpoint to also query the database to check if the message is planner-related, adding latency and coupling.

### Why Reuse `planner_service.get_event_priority()`?

The priority calculation (URGENT / HIGH / NORMAL) is already implemented and tested in `planner_service.py`. Duplicating the logic in `study_advisor_service.py` would introduce a maintenance risk if the thresholds ever change. By importing and calling the existing function, the Study Advisor always uses the exact same priority values the student sees in the Planner panel.

### Why Return 200 Even on Errors?

The Study Advisor endpoint returns `200 OK` with a human-readable `answer` string in all cases — including no-events and Gemini failures. This simplifies the frontend: `if (res.ok)` is always true for non-network errors, and the `answer` field always contains something displayable. The alternative (returning 500 or 503 for Gemini failures) would require the frontend to handle error status codes separately.

---

## 13. Future Improvements

| Improvement | Description |
|---|---|
| **Streaming Study Advisor** | Convert to SSE so the response is "typed out" like the general chat |
| **Chat history integration** | Save Study Advisor conversations to `ChatMessage` table for history view |
| **User scoping** | Use `user_id` from the `AcademicEvent` table once authentication is added, so advice is personalized per user |
| **Proactive alerts** | Run a scheduled service that calls Study Advisor automatically when an URGENT event appears and pushes a notification |
| **Study plan generation** | Extend the service to generate a full weekly schedule stored in the existing `StudyPlan` model |
| **Weakness-aware advice** | Cross-reference Planner events with grade data (from the Noten feature) to recommend more study time for subjects where the student has lower grades |
| **Context caching** | Cache the event context for a short TTL (e.g., 60 seconds) to avoid redundant DB queries on repeated questions in the same session |

---

## 14. How to Present This Feature

### What the Audience Should Understand

1. **The AI is grounded in real data.** Every recommendation Gemini gives is based on events that the student actually entered. It does not hallucinate deadlines. This is enforced by the system prompt and by the fact that the only context passed to Gemini comes from the database.

2. **The integration is seamless.** The student does not switch to a different interface — they just type in the same chat they have always used. The routing is invisible.

3. **Existing features are 100% intact.** The RAG-based general chat, Calendar, Grades, Job Agent, Planner, and Quiz panels all work exactly as before. The Study Advisor is a purely additive feature.

### Key Points to Explain

- **Context injection is the core pattern.** The Study Advisor demonstrates one of the most important GenAI engineering patterns: instead of asking a generic AI a generic question, you inject structured real-world data into the prompt and ask the AI to reason over it. This is more reliable than RAG for structured database queries.

- **The system prompt is a behavioral contract.** Show the system prompt and explain that it tells Gemini exactly what role to play, what rules to follow, and how to format output. Without it, Gemini could invent events or give generic advice.

- **Keyword routing is practical but imperfect.** Acknowledge that keyword matching can produce false positives (e.g., "exam" in "explain how a SQL exam schema works" would trigger the Study Advisor). In a production system, this could be replaced with an intent classifier or a small LLM call.

### Live Demo Script

1. Open the Planner tab and add 3 events:
   - An exam in 5 days
   - An assignment in 11 days
   - A presentation in 25 days
2. Close the Planner tab.
3. In the chat, type: **"What should I focus on this week?"**
4. Point out: the response references the actual events by name, gives a workload split, and recommends specific actions for today.
5. Type: **"Am I at risk of missing a deadline?"**
6. Point out: Gemini explains which event is highest risk and why, using the days remaining values.
7. Open DevTools → Network tab → show the call to `/api/ai/study-advisor` and the JSON response.
8. Type: **"Explain polymorphism in Java"** — point out that this goes through the original streaming chat (no Study Advisor).
9. Open `http://localhost:8080/docs` and show the new `POST /api/ai/study-advisor` endpoint in the Swagger UI.

### Why This Feature Is Valuable

- It demonstrates **context-grounded AI**: the model's output is anchored to real structured data, making it far more useful than a generic study advice chatbot.
- It shows **full-stack AI integration**: Vue 3 frontend → keyword routing → FastAPI endpoint → SQLAlchemy async query → Gemini API with system prompt → markdown-rendered response.
- It proves the value of the Planner MVP: without the event data collected by the Planner feature, the Study Advisor has nothing to work with. The two features are designed to reinforce each other.

---

## 15. Summary

The AI Study Advisor connects the Planner's structured event data to Google Gemini, turning a list of academic deadlines into personalized, actionable study recommendations delivered directly in the existing chat interface.

**3 new files created:**
- `backend/app/services/study_advisor_service.py` — Fetches events, builds context, calls Gemini with system prompt
- `backend/app/api/v1/study_advisor.py` — Single-endpoint FastAPI router
- `documentation/study-advisor.md` — This documentation file

**2 existing files modified:**
- `backend/app/main.py` — Router imported and registered
- `frontend/src/App.vue` — `isPlannerQuestion()` method and Study Advisor routing block added to `sendPrompt()`

**0 existing features broken.** The general RAG chat, Planner, Calendar, Grades, Job Agent, and Quiz features are all untouched and fully functional.

The feature follows the exact same patterns already established in the project: the same Gemini client, the same async SQLAlchemy session injection, the same router registration, and the same Vue reactive chat display.
