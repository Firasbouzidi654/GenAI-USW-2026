from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.attempt_answer import AttemptAnswer
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_question import QuizQuestion
from app.services.tutor_service import generate_quiz

router = APIRouter(prefix="/api/tutor")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateQuizRequest(BaseModel):
    source_documents: list[str] = Field(..., min_length=1)
    num_questions: int = Field(10, ge=1, le=20)
    course_name: str | None = None


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


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------

@router.post("/quiz/generate", response_model=QuizWithQuestionsOut, status_code=201)
async def create_quiz(body: GenerateQuizRequest, db: AsyncSession = Depends(get_db)):
    try:
        quiz, questions = await generate_quiz(
            source_documents=body.source_documents,
            num_questions=body.num_questions,
            db=db,
            course_name=body.course_name,
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
