"""Case model — the central entity for each parent's dispute."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CaseStatus(str, enum.Enum):
    INTAKE = "intake"
    RESEARCHING = "researching"
    PLANNING = "planning"
    ACTIVE = "active"  # Working through strategy steps
    ESCALATING = "escalating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)

    # Basic info
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # billing, safety, governance, coaching, eligibility, other
    club_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sport: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Structured intake data
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str] = mapped_column(String(20), default="medium")  # low, medium, high, critical
    risk_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # ["athlete_safety", "retaliation", "eligibility", "financial", "child_welfare"]
    people_involved: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # [{"name": "...", "role": "coach/board/parent"}]
    prior_attempts: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline_start: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ISO date

    # Agent outputs
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.INTAKE)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)  # 0=internal, 1=governing body, 2=formal complaint, 3=legal
    strategy_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # [{"step": "...", "due": "...", "priority": "..."}]
    missing_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # ["Need copy of bylaws", ...]

    # LangGraph integration
    langgraph_thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="cases")  # noqa: F821
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="case", cascade="all, delete-orphan")  # noqa: F821
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(back_populates="case", cascade="all, delete-orphan")  # noqa: F821
    timeline_events: Mapped[list["TimelineEvent"]] = relationship(back_populates="case", cascade="all, delete-orphan")  # noqa: F821
    drafts: Mapped[list["Draft"]] = relationship(back_populates="case", cascade="all, delete-orphan")  # noqa: F821
