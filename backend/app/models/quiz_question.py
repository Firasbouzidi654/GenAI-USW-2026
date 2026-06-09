from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(
        Enum("MC", "TF", name="quiz_question_type"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    correct_answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)