"""Keyword-based pre-filter — runs before Gemini sees any email.

Cuts low-value mail (parties, newsletters, mailing-list digests, ads) out of
the pipeline in plain Python so Gemini only ever processes emails that are
actually likely to matter for studies. This is a cheap heuristic, not a
classifier - false positives/negatives are expected and fine, the goal is
reducing token usage and noise, not perfect precision.
"""

from __future__ import annotations

from app.services.email_models import FetchedEmail

# Each category is counted at most once per email (a repeated word shouldn't
# dominate the score) - the category names exist for readability/tuning only.
_POSITIVE_KEYWORDS: dict[str, list[str]] = {
    "exam": ["prüfung", "klausur", "exam", "prüfungsleistung", "klausurtermin"],
    "assignment": [
        "abgabe", "assignment", "pcü", "hausarbeit", "projekt", "beleg",
        "belegarbeit", "submission",
    ],
    "urgent": ["reminder", "fällig", "deadline", "frist", "heute", "morgen", "dringend"],
    "learning": [
        "moodle", "feedback", "review", "vorlesung", "seminar", "übung",
        "note", "noten", "klausurtermin",
    ],
    "admin": [
        "immatrikulation", "rückmeldung", "prüfungsamt", "stundenplan",
        "raumänderung", "ausfall", "anmeldefrist", "praktikum", "internship",
        "bewerbungsfrist",
    ],
}

# Any single hit here is a strong noise signal and is weighted accordingly.
_NEGATIVE_KEYWORDS = [
    "sommerfest", "karaoke", "spieleabend", "picknick", "kalligrafie",
    "party", "kostenlose drinks", "kostenlose getränke", " dj ", "gewinnspiel",
    "rabatt", "werbung", "sonderangebot", "stellenanzeige", "jobbörse",
    "nachrichtensammlung", "mailingliste", "abbestellen", "unsubscribe",
    "austragen", "spielbegeisterte",
]

# Sender domains used for student-club/event mailing lists, distinct from the
# official htw-berlin.de / student.htw-berlin.de academic domains. Kept
# narrow on purpose - generic "noreply@htw-berlin.de" senders legitimately
# carry important Moodle deadline reminders and must NOT be filtered by sender alone.
_NOISE_SENDER_HINTS = ["students-htw.de", "lists.htw-berlin.de"]

_POSITIVE_WEIGHT = 2
_NEGATIVE_WEIGHT = 5
_NOISE_SENDER_WEIGHT = 3

# Minimum score to be considered "important enough to send to Gemini".
DEFAULT_THRESHOLD = 2


def score_email(email: FetchedEmail) -> int:
    """Heuristic relevance score - higher means more likely study-related."""
    text = f"{email.subject}\n{email.body}".lower()
    sender = email.sender.lower()

    score = 0
    for keywords in _POSITIVE_KEYWORDS.values():
        if any(kw in text for kw in keywords):
            score += _POSITIVE_WEIGHT

    for kw in _NEGATIVE_KEYWORDS:
        if kw in text:
            score -= _NEGATIVE_WEIGHT

    if any(hint in sender for hint in _NOISE_SENDER_HINTS):
        score -= _NOISE_SENDER_WEIGHT

    return score


def filter_important_emails(
    emails: list[FetchedEmail],
    threshold: int = DEFAULT_THRESHOLD,
) -> list[FetchedEmail]:
    """Keeps only emails scoring >= threshold, preserving original (newest-first) order."""
    return [e for e in emails if score_email(e) >= threshold]
