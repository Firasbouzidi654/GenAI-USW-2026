from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CurriculumModule(Base):
    """Ein Modul aus dem Modulhandbuch inkl. Vorgänger-Beziehungen (baut_auf).

    Aus dem hochgeladenen Modulhandbuch-PDF per LLM extrahiert. Ermöglicht dem
    Evaluator, bei Wissenslücken die Vorgängermodule zum Wiederholen zu empfehlen.
    """

    __tablename__ = "curriculum_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    semester: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Liste von Modulnamen, auf denen dieses Modul aufbaut (Vorgänger)
    prerequisites: Mapped[list] = mapped_column(JSON, default=list)
    # Kompetenzen/Themen, die das Modul vermittelt
    competencies: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
