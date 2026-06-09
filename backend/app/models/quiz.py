from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    source_documents: Mapped[list] = mapped_column(JSON)
    course_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    question_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )