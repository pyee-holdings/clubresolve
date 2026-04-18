"""CaseQuestion — structured clarifying questions the agent asks the user.

These are first-class work items. Every intake gets a readiness review that
produces a prioritized list of questions; the user answers (or dismisses)
them one at a time. Planning should wait until critical questions are resolved.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class QuestionStatus(str, enum.Enum):
    OPEN = "open"             # Awaiting user response
    ANSWERED = "answered"     # User provided an answer
    DISMISSED = "dismissed"   # User explicitly skipped (not applicable)


class QuestionPriority(str, enum.Enum):
    CRITICAL = "critical"     # Blocks meaningful planning
    IMPORTANT = "important"   # Significantly improves the plan
    NICE_TO_HAVE = "nice_to_have"


class CaseQuestion(Base):
    __tablename__ = "case_questions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cases.id"), nullable=False, index=True
    )

    # The question
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  # Why we're asking
    category: Mapped[str] = mapped_column(String(40), default="general")
    # Categories: people, timeline, evidence, policy, outcome, general
    priority: Mapped[QuestionPriority] = mapped_column(
        Enum(QuestionPriority), default=QuestionPriority.IMPORTANT
    )

    # Who asked
    generated_by: Mapped[str] = mapped_column(String(60), default="intake_review_agent")

    # Answer
    status: Mapped[QuestionStatus] = mapped_column(
        Enum(QuestionStatus), default=QuestionStatus.OPEN, index=True
    )
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    case: Mapped["Case"] = relationship(back_populates="questions")  # noqa: F821
