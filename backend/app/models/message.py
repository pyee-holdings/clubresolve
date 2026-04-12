"""Chat message model — denormalized for fast API queries."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id"), nullable=False, index=True)

    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user", "assistant"
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "navigator", "counsel", "vault", "drafts"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Tool calls, citations, confidence levels

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="messages")  # noqa: F821
