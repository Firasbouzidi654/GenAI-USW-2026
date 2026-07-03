import pytest
from fastapi import HTTPException

from app.api.v1.tutor import AnswerIn, SubmitAttemptRequest, submit_attempt
from app.models.quiz import Quiz
from app.models.quiz_question import QuizQuestion


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None

    def scalars(self):
        return _ScalarResult(self._values)


class _FakeDb:
    def __init__(self, execute_results):
        self._execute_results = list(execute_results)
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, _statement):
        return _ExecuteResult(self._execute_results.pop(0))

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.added[0].id = 123

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _quiz(quiz_id=1):
    return Quiz(
        id=quiz_id,
        title="Quiz",
        source_documents=["doc.pdf"],
        course_name="Course",
        question_count=1,
    )


def _question(question_id=10, quiz_id=1):
    return QuizQuestion(
        id=question_id,
        quiz_id=quiz_id,
        position=1,
        question_type="MC",
        question_text="Question?",
        options=["A", "B"],
        correct_answer="A",
        explanation="Because.",
    )


@pytest.mark.asyncio
async def test_submit_attempt_rejects_duplicate_question_ids():
    db = _FakeDb([])
    body = SubmitAttemptRequest(
        answers=[
            AnswerIn(question_id=10, given_answer="A"),
            AnswerIn(question_id=10, given_answer="B"),
        ]
    )

    with pytest.raises(HTTPException) as exc:
        await submit_attempt(1, body, db)

    assert exc.value.status_code == 422
    assert not db.committed


@pytest.mark.asyncio
async def test_submit_attempt_rejects_question_from_another_quiz():
    db = _FakeDb([[_quiz(1)], []])
    body = SubmitAttemptRequest(answers=[AnswerIn(question_id=99, given_answer="A")])

    with pytest.raises(HTTPException) as exc:
        await submit_attempt(1, body, db)

    assert exc.value.status_code == 422
    assert "gehört nicht zu diesem Quiz" in exc.value.detail
    assert not db.committed


@pytest.mark.asyncio
async def test_submit_attempt_scores_and_persists_valid_answers():
    db = _FakeDb([[_quiz(1)], [_question(10, 1)]])
    body = SubmitAttemptRequest(answers=[AnswerIn(question_id=10, given_answer="A")])

    result = await submit_attempt(1, body, db)

    assert result.score == 1
    assert result.total_questions == 1
    assert result.percentage == 100.0
    assert db.committed
