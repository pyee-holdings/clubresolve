"""EvidenceRequest — structured "please provide X" work items.

The killer feature. Disputes drag on for months; parents lose track of what
they have. Every evidence request is a first-class, trackable item with a
specific ask, a reason, and a clear fulfillment state. Fulfilling it creates
an EvidenceItem and links it back so the lineage (agent asked → user provided
→ item in the vault) is preserved.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EvidenceRequestStatus(str, enum.Enum):
    OPEN = "open"               # Waiting on the user
    FULFILLED = "fulfilled"     # EvidenceItem has been attached
    UNAVAILABLE = "unavailable" # User has explicitly said they don't have it
    DISMISSED = "dismissed"     # No longer relevant (agent or user)


class EvidenceRequest(Base):
    __tablename__ = "evidence_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id"), nullable=False, index=True
    )

    # What's needed
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # evidence_type mirrors EvidenceItem.evidence_type — keep the vocabularies aligned.
    evidence_type: Mapped[str] = mapped_column(String(50), default="document")
    expected_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ISO date if known

    # Importance
    priority: Mapped[str] = mapped_column(String(20), default="important")
    # critical | important | nice_to_have

    # Where did this request come from
    generated_by: Mapped[str] = mapped_column(String(60), default="intake_review_agent")

    # Fulfillment
    status: Mapped[EvidenceRequestStatus] = mapped_column(
        Enum(EvidenceRequestStatus), default=EvidenceRequestStatus.OPEN, index=True
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evidence_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evidence_items.id"), nullable=True
    )
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="evidence_requests")  # noqa: F821
