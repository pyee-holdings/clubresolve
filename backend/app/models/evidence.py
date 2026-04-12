"""Evidence and timeline models — the structured evidence vault."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id"), nullable=False)

    # Content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)  # email, screenshot, document, receipt, correspondence, policy, note, contract
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)  # "Email from coach on Jan 5", "Club bylaws section 4.2"

    # Storage
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # For uploaded files
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # For text-based evidence or extracted text
    extracted_snippets: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Key quotes/sections pulled from document

    # Metadata
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # ["billing", "contract", "safety"]
    collected_by: Mapped[str] = mapped_column(String(20), default="user")  # "user" or "evidence_agent"
    event_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # When the evidence event occurred (ISO date)

    # Analytical fields
    contradicts_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("evidence_items.id"), nullable=True)
    unanswered_questions: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Questions this evidence raises

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="evidence_items")  # noqa: F821


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id"), nullable=False)

    event_date: Mapped[str] = mapped_column(String(20), nullable=False)  # ISO date
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Links to supporting evidence
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Where this event info came from
    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # incident, communication, deadline, action

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="timeline_events")  # noqa: F821
