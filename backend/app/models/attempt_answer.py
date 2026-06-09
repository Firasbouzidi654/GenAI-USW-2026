from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AttemptAnswer(Base):
    __tablename__ = "quiz_attempt_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(Integer, ForeignKey("quiz_attempts.id", ondelete="CASCADE"))
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("quiz_questions.id", ondelete="CASCADE"))
    given_answer: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean)