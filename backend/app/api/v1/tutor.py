from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.attempt_answer import AttemptAnswer
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_question import QuizQuestion
from app.agents.tutor_agent import generate_quiz_review
from app.services.tutor_service import generate_quiz

router = APIRouter(prefix="/api/tutor")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateQuizRequest(BaseModel):
    source_documents: list[str] = Field(..., min_length=1)
    num_questions: int = Field(10, ge=1, le=20)
    course_name: str | None = None
    chat_id: str | None = None
    user_id: str = "local"


class QuestionOut(BaseModel):
    id: int
    position: int
    question_type: str
    question_text: str
    options: list[str] | None

    model_config = {"from_attributes": True}


class QuizOut(BaseModel):
    id: int
    title: str
    source_documents: list[str]
    course_name: str | None
    question_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QuizWithQuestionsOut(QuizOut):
    questions: list[QuestionOut]


class AnswerIn(BaseModel):
    question_id: int
    given_answer: str


class SubmitAttemptRequest(BaseModel):
    answers: list[AnswerIn] = Field(..., min_length=1)


class AnswerResultOut(BaseModel):
    question_id: int
    given_answer: str
    correct_answer: str
    is_correct: bool
    explanation: str | None


class AttemptResultOut(BaseModel):
    attempt_id: int
    score: int
    total_questions: int
    percentage: float
    answers: list[AnswerResultOut]


class ReviewRequest(BaseModel):
    attempt_id: int


class ReviewOut(BaseModel):
    review: str
    source_documents: list[str]
    course_name: str | None
    score: int
    total_questions: int
    percentage: float


class QuestionStatsOut(BaseModel):
    question_id: int
    question_text: str
    question_type: str
    correct_count: int
    total_count: int
    success_rate: float


class StatsOut(BaseModel):
    total_attempts: int
    average_score: float
    weak_questions: list[QuestionStatsOut]
    strong_questions: list[QuestionStatsOut]


class TopicMasteryOut(BaseModel):
    topic: str
    score: int                 # 0–100, Anteil richtiger Antworten
    correct: int
    total: int
    attempts: int
    level: str                 # "stark" | "ok" | "schwach"
    source_documents: list[str]


class ProfileOut(BaseModel):
    overall_score: int
    total_answered: int
    topics: list[TopicMasteryOut]
    weak_topics: list[str]


class WeaknessQuizRequest(BaseModel):
    num_questions: int = Field(10, ge=1, le=20)


# Schwelle, ab der ein Thema als "beherrscht" gilt
_STRONG_THRESHOLD = 80
_WEAK_THRESHOLD = 60


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------

@router.post("/quiz/generate", response_model=QuizWithQuestionsOut, status_code=201)
async def create_quiz(body: GenerateQuizRequest, db: AsyncSession = Depends(get_db)):
    # Falls kein Modul-/Kursname gesetzt ist (z.B. sofort nach Upload generiert),
    # das passende Modul aus dem Modulhandbuch ermitteln → korrekte Gruppierung im Profil.
    course_name = (body.course_name or "").strip() or None
    if not course_name:
        try:
            from app.services.curriculum_service import suggest_module
            course_name = await suggest_module(body.source_documents, db, body.user_id)
        except Exception:
            course_name = None

    try:
        quiz, questions = await generate_quiz(
            source_documents=body.source_documents,
            num_questions=body.num_questions,
            db=db,
            course_name=course_name,
            chat_id=body.chat_id,
            user_id=body.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return QuizWithQuestionsOut(
        **QuizOut.model_validate(quiz).model_dump(),
        questions=[QuestionOut.model_validate(q) for q in questions],
    )


@router.get("/quizzes", response_model=list[QuizOut])
async def list_quizzes(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Quiz).order_by(Quiz.created_at.desc()))
        return [QuizOut.model_validate(q) for q in result.scalars().all()]
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")


@router.get("/quiz/{quiz_id}", response_model=QuizWithQuestionsOut)
async def get_quiz(quiz_id: int, db: AsyncSession = Depends(get_db)):
    try:
        quiz_result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
        quiz = quiz_result.scalar_one_or_none()
        if quiz is None:
            raise HTTPException(status_code=404, detail="Quiz nicht gefunden.")

        q_result = await db.execute(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.position)
        )
        questions = q_result.scalars().all()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    return QuizWithQuestionsOut(
        **QuizOut.model_validate(quiz).model_dump(),
        questions=[QuestionOut.model_validate(q) for q in questions],
    )


@router.post("/quiz/{quiz_id}/submit", response_model=AttemptResultOut, status_code=201)
async def submit_attempt(quiz_id: int, body: SubmitAttemptRequest, db: AsyncSession = Depends(get_db)):
    try:
        quiz_result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
        if quiz_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Quiz nicht gefunden.")

        question_ids = [a.question_id for a in body.answers]
        q_result = await db.execute(
            select(QuizQuestion).where(QuizQuestion.id.in_(question_ids))
        )
        questions_by_id = {q.id: q for q in q_result.scalars().all()}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    answer_results: list[AnswerResultOut] = []
    score = 0

    for answer in body.answers:
        question = questions_by_id.get(answer.question_id)
        if question is None:
            raise HTTPException(
                status_code=422,
                detail=f"Frage {answer.question_id} gehört nicht zu diesem Quiz.",
            )
        is_correct = answer.given_answer.strip() == question.correct_answer
        if is_correct:
            score += 1
        answer_results.append(AnswerResultOut(
            question_id=question.id,
            given_answer=answer.given_answer,
            correct_answer=question.correct_answer,
            is_correct=is_correct,
            explanation=question.explanation,
        ))

    total = len(answer_results)
    try:
        attempt = QuizAttempt(quiz_id=quiz_id, score=score, total_questions=total)
        db.add(attempt)
        await db.flush()

        for res in answer_results:
            db.add(AttemptAnswer(
                attempt_id=attempt.id,
                question_id=res.question_id,
                given_answer=res.given_answer,
                is_correct=res.is_correct,
            ))
        await db.commit()
    except Exception:
        raise HTTPException(status_code=503, detail="Ergebnis konnte nicht gespeichert werden.")

    return AttemptResultOut(
        attempt_id=attempt.id,
        score=score,
        total_questions=total,
        percentage=round(score / total * 100, 1) if total else 0.0,
        answers=answer_results,
    )


@router.post("/quiz/{quiz_id}/review", response_model=ReviewOut)
async def review_attempt(quiz_id: int, body: ReviewRequest, db: AsyncSession = Depends(get_db)):
    """Ausführliche Nachbesprechung eines Quiz-Versuchs: geht die falschen Antworten
    durch und empfiehlt das passende Material zum Wiederholen."""
    quiz = (await db.execute(select(Quiz).where(Quiz.id == quiz_id))).scalar_one_or_none()
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz nicht gefunden.")
    attempt = (await db.execute(
        select(QuizAttempt).where(QuizAttempt.id == body.attempt_id, QuizAttempt.quiz_id == quiz_id)
    )).scalar_one_or_none()
    if attempt is None:
        raise HTTPException(status_code=404, detail="Quiz-Versuch nicht gefunden.")

    ans_rows = (await db.execute(
        select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id)
    )).scalars().all()
    q_ids = [a.question_id for a in ans_rows]
    questions = {
        q.id: q for q in (await db.execute(
            select(QuizQuestion).where(QuizQuestion.id.in_(q_ids))
        )).scalars().all()
    }
    wrong_items: list[dict] = []
    for a in ans_rows:
        if a.is_correct:
            continue
        q = questions.get(a.question_id)
        if q is None:
            continue
        wrong_items.append({
            "question": q.question_text,
            "given": a.given_answer,
            "correct": q.correct_answer,
            "explanation": q.explanation,
        })

    try:
        review = await generate_quiz_review(
            quiz_title=quiz.title,
            source_documents=quiz.source_documents or [],
            course_name=quiz.course_name,
            score=attempt.score,
            total=attempt.total_questions,
            wrong_items=wrong_items,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    pct = round(attempt.score / attempt.total_questions * 100, 1) if attempt.total_questions else 0.0
    return ReviewOut(
        review=review,
        source_documents=quiz.source_documents or [],
        course_name=quiz.course_name,
        score=attempt.score,
        total_questions=attempt.total_questions,
        percentage=pct,
    )


@router.get("/stats", response_model=StatsOut)
async def get_stats(db: AsyncSession = Depends(get_db)):
    try:
        attempts_result = await db.execute(select(QuizAttempt))
        all_attempts = attempts_result.scalars().all()
        total_attempts = len(all_attempts)
        avg_score = (
            round(sum(a.score / a.total_questions * 100 for a in all_attempts) / total_attempts, 1)
            if total_attempts else 0.0
        )

        # Pro Frage: Anzahl Versuche und korrekte Antworten aggregieren
        answers_result = await db.execute(select(AttemptAnswer))
        all_answers = answers_result.scalars().all()

        stats_by_question: dict[int, dict] = {}
        for ans in all_answers:
            s = stats_by_question.setdefault(ans.question_id, {"correct": 0, "total": 0})
            s["total"] += 1
            if ans.is_correct:
                s["correct"] += 1

        if not stats_by_question:
            return StatsOut(
                total_attempts=total_attempts,
                average_score=avg_score,
                weak_questions=[],
                strong_questions=[],
            )

        question_ids = list(stats_by_question.keys())
        q_result = await db.execute(
            select(QuizQuestion).where(QuizQuestion.id.in_(question_ids))
        )
        questions_by_id = {q.id: q for q in q_result.scalars().all()}

        question_stats: list[QuestionStatsOut] = []
        for qid, counts in stats_by_question.items():
            q = questions_by_id.get(qid)
            if q is None:
                continue
            rate = counts["correct"] / counts["total"] if counts["total"] else 0.0
            question_stats.append(QuestionStatsOut(
                question_id=qid,
                question_text=q.question_text,
                question_type=q.question_type,
                correct_count=counts["correct"],
                total_count=counts["total"],
                success_rate=round(rate * 100, 1),
            ))

        question_stats.sort(key=lambda x: x.success_rate)
        weak = [q for q in question_stats if q.success_rate < 60][:5]
        strong = [q for q in reversed(question_stats) if q.success_rate >= 80][:5]

    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    return StatsOut(
        total_attempts=total_attempts,
        average_score=avg_score,
        weak_questions=weak,
        strong_questions=strong,
    )


# ---------------------------------------------------------------------------
# Profil: Themen-Beherrschung (Score 0–100 pro Kurs/Thema)
# ---------------------------------------------------------------------------

def _module_key(quiz: Quiz) -> str:
    """Stabiler Gruppierungs-Schlüssel pro Modul.

    Primär die Quelldokumente (gleiche Datei(en) = gleiches Modul), sonst der
    Kursname, sonst der Titel. So erzeugen mehrere Quizze desselben Moduls EINEN
    Profil-Eintrag, dessen Score sich aktualisiert — statt eines Eintrags je Quiz.
    """
    docs = sorted(quiz.source_documents or [])
    if docs:
        return "docs:" + "|".join(docs)
    if quiz.course_name and quiz.course_name.strip():
        return "course:" + quiz.course_name.strip().lower()
    return "title:" + (quiz.title or "Allgemein").lower()


def _clean_doc_name(name: str) -> str:
    return name.rsplit(".", 1)[0].replace("_", " ").strip()


async def _compute_topic_mastery(db: AsyncSession) -> list[dict]:
    """Aggregiert die beantworteten Quizfragen pro MODUL (nicht pro Quiz).

    Score = Anteil richtiger Antworten über alle Versuche des Moduls (0–100).
    """
    answers = (await db.execute(select(AttemptAnswer))).scalars().all()
    if not answers:
        return []

    questions = (await db.execute(select(QuizQuestion))).scalars().all()
    quiz_by_question = {q.id: q.quiz_id for q in questions}

    quizzes = (await db.execute(select(Quiz))).scalars().all()
    quiz_by_id = {q.id: q for q in quizzes}

    # Pro Modul aggregieren (Schlüssel stabil über mehrere Quizze)
    agg: dict[str, dict] = {}
    for ans in answers:
        quiz_id = quiz_by_question.get(ans.question_id)
        quiz = quiz_by_id.get(quiz_id) if quiz_id else None
        if quiz is None:
            continue
        key = _module_key(quiz)
        a = agg.setdefault(key, {
            "correct": 0, "total": 0, "quiz_ids": set(), "docs": set(), "course_names": [],
        })
        a["total"] += 1
        if ans.is_correct:
            a["correct"] += 1
        a["quiz_ids"].add(quiz_id)
        for d in (quiz.source_documents or []):
            a["docs"].add(d)
        if quiz.course_name and quiz.course_name.strip() and not quiz.course_name.startswith("Schwächen-Quiz"):
            a["course_names"].append(quiz.course_name.strip())

    topics: list[dict] = []
    for a in agg.values():
        # Anzeigename: Kursname (häufigster) > erstes Dokument > "Allgemein"
        if a["course_names"]:
            label = max(set(a["course_names"]), key=a["course_names"].count)
        elif a["docs"]:
            label = _clean_doc_name(sorted(a["docs"])[0])
        else:
            label = "Allgemein"
        score = round(a["correct"] / a["total"] * 100) if a["total"] else 0
        level = "stark" if score >= _STRONG_THRESHOLD else "ok" if score >= _WEAK_THRESHOLD else "schwach"
        topics.append({
            "topic": label,
            "score": score,
            "correct": a["correct"],
            "total": a["total"],
            "attempts": len(a["quiz_ids"]),
            "level": level,
            "source_documents": sorted(a["docs"]),
        })
    topics.sort(key=lambda t: t["score"])
    return topics


@router.get("/profile", response_model=ProfileOut)
async def get_profile(db: AsyncSession = Depends(get_db)):
    """Lernprofil: pro Thema ein Score 0–100, berechnet aus den Quiz-Ergebnissen."""
    try:
        topics = await _compute_topic_mastery(db)
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    total_answered = sum(t["total"] for t in topics)
    total_correct = sum(t["correct"] for t in topics)
    overall = round(total_correct / total_answered * 100) if total_answered else 0
    weak_topics = [t["topic"] for t in topics if t["level"] == "schwach"]

    return ProfileOut(
        overall_score=overall,
        total_answered=total_answered,
        topics=[TopicMasteryOut(**t) for t in topics],
        weak_topics=weak_topics,
    )


@router.delete("/stats", status_code=204)
async def reset_stats(db: AsyncSession = Depends(get_db)):
    """Setzt alle Quiz-Statistiken zurück (löscht Versuche + Antworten, behält Quizze)."""
    try:
        await db.execute(delete(AttemptAnswer))
        await db.execute(delete(QuizAttempt))
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Zurücksetzen fehlgeschlagen.")


@router.post("/quiz/weakness", response_model=QuizWithQuestionsOut, status_code=201)
async def create_weakness_quiz(body: WeaknessQuizRequest, db: AsyncSession = Depends(get_db)):
    """Erzeugt ein Quiz gezielt aus den schwachen Themen des Lernprofils."""
    try:
        topics = await _compute_topic_mastery(db)
    except Exception:
        raise HTTPException(status_code=503, detail="Datenbank nicht erreichbar.")

    weak = [t for t in topics if t["level"] == "schwach"]
    if not weak:
        # Kein schwaches Thema → das schwächste vorhandene nehmen
        weak = topics[:1]
    if not weak:
        raise HTTPException(
            status_code=422,
            detail="Noch keine Quiz-Ergebnisse vorhanden. Mach zuerst ein paar Quizze.",
        )

    # Dokumente der schwachen Themen sammeln
    docs = sorted({d for t in weak for d in t["source_documents"]})
    if not docs:
        raise HTTPException(
            status_code=422,
            detail="Für die schwachen Themen sind keine Quelldokumente mehr vorhanden.",
        )

    topic_names = ", ".join(t["topic"] for t in weak)
    try:
        quiz, questions = await generate_quiz(
            source_documents=docs,
            num_questions=body.num_questions,
            db=db,
            course_name=f"Schwächen-Quiz: {topic_names}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return QuizWithQuestionsOut(
        **QuizOut.model_validate(quiz).model_dump(),
        questions=[QuestionOut.model_validate(q) for q in questions],
    )
