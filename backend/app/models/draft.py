"""Draft model — Draft Studio generated communications."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DraftStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    SENT = "sent"


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id"), nullable=False)

    # Content
    draft_type: Mapped[str] = mapped_column(String(50), nullable=False)  # email, letter, complaint, memo, question
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Who this is addressed to
    tone: Mapped[str] = mapped_column(String(50), default="professional")  # professional, firm, conciliatory

    # Status
    status: Mapped[DraftStatus] = mapped_column(Enum(DraftStatus), default=DraftStatus.DRAFT)
    generated_by: Mapped[str] = mapped_column(String(50), default="drafts_agent")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="drafts")  # noqa: F821
