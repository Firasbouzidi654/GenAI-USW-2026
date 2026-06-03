# GenAI-USW-2026

# Adaptive Study & Career Agent

## Overview

The Adaptive Study & Career Agent is an AI-powered multi-agent system that helps students learn more effectively while simultaneously preparing them for internships and job opportunities.

Unlike traditional chatbots, the system continuously analyzes the user's learning progress, identifies knowledge gaps, and adapts study plans accordingly. At the same time, it uses the user's academic achievements, completed courses, uploaded materials, and demonstrated skills to search for relevant internships and jobs.

The main idea is simple:

**The better you learn, the better career opportunities the system can find for you.**

---

## Problem Statement

Students often face two separate challenges:

1. Organizing their studies and preparing efficiently for exams.
2. Finding internships and jobs that match their skills and academic profile.

Most platforms treat these tasks separately. Learning platforms help students study, while job platforms help them search for opportunities.

This project combines both into a single intelligent system.

---

## Key Features

### 1. Adaptive Learning System

Users can upload:

* Lecture slides
* PDFs
* Course notes
* Assignments
* Study materials

The system creates a Retrieval-Augmented Generation (RAG) knowledge base from the uploaded content.

### 2. Personalized Study Planner

A Planner Agent creates customized study schedules based on:

* Exam dates
* Available study time
* Learning goals
* Previous quiz performance
* Mastered concepts
* Weak areas

### 3. Intelligent Tutor Agent

The Tutor Agent can:

* Generate quizzes
* Ask exam-style questions
* Evaluate answers
* Provide explanations
* Adjust difficulty dynamically

### 4. Learning Analytics

The Evaluator Agent tracks:

* Progress over time
* Concept mastery
* Repeated mistakes
* Weak subjects

Instead of analyzing only individual wrong answers, the system detects recurring conceptual gaps.

### 5. Career Discovery Agent

The Career Agent continuously analyzes:

* User CV
* Skills demonstrated during learning
* Completed courses
* Certificates
* Strong academic topics

The agent searches for:

* Internships
* Student jobs
* Graduate positions
* Entry-level opportunities

from platforms such as LinkedIn, StepStone, Indeed, and company career pages.

### 6. Intelligent Job Matching

Each job description is compared with the user's profile using semantic matching.

The system calculates a compatibility score based on:

* Skills
* Technologies
* Academic background
* Interests
* Demonstrated knowledge



---

## Example Workflow

1. User uploads lecture slides and notes.
2. The system creates a RAG knowledge base.
3. The Tutor Agent generates quizzes.
4. The Evaluator Agent detects strengths and weaknesses.
5. The Career Agent analyzes acquired skills.
6. Relevant internships and jobs are automatically searched.
7. Missing skills are identified.
8. The Study Agent creates a learning plan to acquire those skills.
9. The system generates application documents when the user is ready to apply.

---

## n8n Job Search Agent Setup

The frontend has a **"Launch Job Search Agent"** button inside the Career panel that manually triggers an n8n workflow via webhook.

### Steps to connect n8n

1. **Replace the Schedule Trigger** in your n8n workflow with a **Webhook** node.
   - In the n8n editor, delete the Schedule Trigger and add a Webhook node as the first node.

2. **Copy the Production Webhook URL**
   - In the Webhook node settings, switch to **Production** mode and copy the URL.
   - It looks like: `https://your-n8n-instance.com/webhook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

3. **Paste it into `backend/.env`**
   ```env
   N8N_JOB_AGENT_WEBHOOK_URL=https://your-n8n-instance.com/webhook/your-webhook-id
   ```

4. **Activate the n8n workflow**
   - Toggle the workflow to **Active** in the top-right corner of the n8n editor.
   - The Production Webhook URL only works when the workflow is active.

5. **Restart the backend** so it picks up the new environment variable:
   ```bash
   uvicorn app.main:app --reload
   ```

6. **Click "Launch Job Search Agent"** in the Career dropdown — the button calls `POST /api/job-agent/run`, which forwards the request to n8n and shows a success or error message.

### API endpoint

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/job-agent/run` | Triggers the n8n webhook and starts the job search workflow |

**Request body (all fields optional):**
```json
{
  "keyword": "Data Analyst",
  "location": "Berlin",
  "experienceLevel": "entry",
  "remote": "true",
  "jobType": "fulltime",
  "easyApply": true
}
```

