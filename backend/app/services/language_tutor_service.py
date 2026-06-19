"""Language Tutor Service — conversational language practice via Gemini, with CEFR/XP progress tracking."""

from __future__ import annotations

import json
import logging
import re

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.gemini_api_key)

SUPPORTED_LANGUAGES = {"English", "German", "French", "Spanish", "Italian"}
CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

_EMA_ALPHA = 0.2  # how fast the stored level reacts to each new estimate — gradual, not jumpy
_XP_PER_TURN = 10
_XP_BONUS_ALREADY_CORRECT = 5

_SYSTEM_PROMPT_TEMPLATE = """
You are a warm, encouraging, real {language} conversation teacher having a live spoken conversation with a student.

The student's current estimated level is {cefr_level} (CEFR scale: A1 = beginner ... C2 = mastery).
Calibrate your vocabulary, sentence complexity, and the difficulty of your next question to match this level,
while gently pushing the student slightly beyond their comfort zone.

For every student message, follow this process before answering:
1. Read and understand what the student MEANT, even if the grammar, word choice, or sentence structure is imperfect.
2. Internally analyze what (if anything) is wrong: grammar, word choice, unnatural phrasing, or sentence structure.
3. React to the CONTENT of what the student said like a real teacher in conversation would — warm, encouraging,
   and specific. Never just say "good job" with no substance.
4. Gently correct mistakes — never make the student feel bad. If the sentence was already correct and natural,
   do NOT invent a correction.
5. Ask exactly ONE natural follow-up question that keeps the conversation going and matches the student's level.

Respond ONLY with valid JSON in this exact schema:
{{
  "reply": "string - your warm, natural reaction to what the student said, IN {language}",
  "correction": "string or null - the corrected version of the student's sentence IN {language}; null if the sentence was already correct and natural",
  "explanation": "string or null - a short, simple explanation (in English) of what was wrong and why; null if there was no correction",
  "vocabulary": [
    {{"word": "string - a useful {language} word or short phrase related to this conversation", "meaning": "string - its English meaning"}}
  ],
  "better_version": "string - a more natural, fluent way a native speaker would phrase what the student was trying to say, IN {language}",
  "next_question": "string - exactly one natural follow-up question IN {language} that continues the conversation and matches the student's level",
  "estimated_cefr": "string - your best-guess CEFR level (A1, A2, B1, B2, C1, or C2) for the grammar, vocabulary range, and sentence complexity of THIS student message only"
}}

Rules:
- Return between 3 and 5 items in "vocabulary".
- Keep "reply" short and conversational (1-2 sentences) — like a real tutor reacting live, not a chatbot.
- "next_question" must always be present and must be a genuine question, not a statement.
- "estimated_cefr" must always be exactly one of: A1, A2, B1, B2, C1, C2 — base it only on this message, even if short.
- If the student's message has no real content (e.g. just "hi"), still react warmly, give 3-5 relevant vocabulary
  words, and ask a natural opening question.
- Never include markdown, code fences, or any text outside the JSON object.
""".strip()

_FALLBACK = {
    "reply": "Sorry, I couldn't process that. Could you try again?",
    "correction": None,
    "explanation": None,
    "vocabulary": [],
    "better_version": None,
    "next_question": None,
    "estimated_cefr": None,
}


def _level_to_score(level: str) -> float:
    try:
        return float(CEFR_LEVELS.index(level) + 1)
    except ValueError:
        return 1.0


def _score_to_level(score: float) -> str:
    idx = max(0, min(len(CEFR_LEVELS) - 1, round(score) - 1))
    return CEFR_LEVELS[idx]


def compute_progress_update(
    current_score: float, current_xp: int, estimated_cefr: str | None, had_correction: bool
) -> tuple[float, int, str]:
    """Pure scoring step run after each tutor turn.

    - The stored level is an exponential moving average over each message's estimated CEFR level,
      so a single easy/hard message can't swing the displayed level — it shifts gradually.
    - XP is a simple engagement counter: +10 per turn, +5 bonus when the student's sentence needed
      no correction at all.
    """
    new_score = current_score
    if estimated_cefr in CEFR_LEVELS:
        observed = _level_to_score(estimated_cefr)
        new_score = current_score * (1 - _EMA_ALPHA) + observed * _EMA_ALPHA

    new_xp = current_xp + _XP_PER_TURN + (0 if had_correction else _XP_BONUS_ALREADY_CORRECT)
    new_level = _score_to_level(new_score)
    return new_score, new_xp, new_level


def _build_contents(history: list[dict], message: str) -> list[types.Content]:
    contents: list[types.Content] = []
    for turn in history:
        role = "model" if turn.get("role") == "assistant" else "user"
        text = turn.get("text", "")
        if text:
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    return contents


def _parse_response(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if not match:
            match = re.search(r"(\{.*\})", raw, re.DOTALL)
        if not match:
            raise ValueError("Gemini-Antwort enthält kein valides JSON.")
        data = json.loads(match.group(1))

    if not isinstance(data, dict) or not data.get("reply"):
        raise ValueError("Gemini-Antwort enthält kein 'reply'-Feld.")

    vocabulary = data.get("vocabulary") or []
    clean_vocab = [
        {"word": str(v.get("word", "")).strip(), "meaning": str(v.get("meaning", "")).strip()}
        for v in vocabulary
        if isinstance(v, dict) and v.get("word")
    ][:5]

    estimated_cefr = data.get("estimated_cefr")
    if estimated_cefr not in CEFR_LEVELS:
        estimated_cefr = None

    return {
        "reply": str(data["reply"]).strip(),
        "correction": (str(data["correction"]).strip() if data.get("correction") else None),
        "explanation": (str(data["explanation"]).strip() if data.get("explanation") else None),
        "vocabulary": clean_vocab,
        "better_version": (str(data["better_version"]).strip() if data.get("better_version") else None),
        "next_question": (str(data["next_question"]).strip() if data.get("next_question") else None),
        "estimated_cefr": estimated_cefr,
    }


async def get_tutor_reply(language: str, message: str, history: list[dict], cefr_level: str = "A1") -> dict:
    """Generates a structured language-tutor reply for one conversation turn.

    Raises:
        RuntimeError: if Gemini fails or returns an unparsable response.
    """
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(language=language, cefr_level=cefr_level)
    contents = _build_contents(history, message)

    try:
        response = await _client.aio.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
            ),
        )
        raw = response.text or ""
    except Exception as exc:
        logger.error("Gemini-Anfrage (Language Tutor) fehlgeschlagen: %s", exc)
        raise RuntimeError("Der Sprachtutor ist momentan nicht erreichbar. Bitte später erneut versuchen.")

    try:
        return _parse_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Language-Tutor-Antwort konnte nicht geparst werden: %s\nRaw: %s", exc, raw[:500])
        return dict(_FALLBACK)
