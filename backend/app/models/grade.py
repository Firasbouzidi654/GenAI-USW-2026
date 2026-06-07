from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    course_name: Mapped[str] = mapped_column(String(512))
    semester: Mapped[str | None] = mapped_column(String(50), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    module_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
