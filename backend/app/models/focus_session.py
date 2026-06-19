from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    focus_minutes: Mapped[float] = mapped_column(Float)
    break_minutes: Mapped[float] = mapped_column(Float)
    completed_cycles: Mapped[int] = mapped_column(Integer)
    total_focus_time: Mapped[float] = mapped_column(Float)
    selected_theme: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
