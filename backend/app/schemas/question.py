"""Pydantic schemas for CaseQuestion — what the API and agent exchange."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.question import QuestionPriority, QuestionStatus


class QuestionDraft(BaseModel):
    """A single question as produced by the intake review agent.

    The agent returns a list of these; the service layer turns them into
    CaseQuestion rows. Kept separate from CaseQuestionResponse so the agent
    output schema can evolve independently of the API shape.
    """

    question: str = Field(..., min_length=3, max_length=2000)
    context: str | None = Field(default=None, max_length=2000)
    category: str = Field(default="general", max_length=40)
    priority: QuestionPriority = QuestionPriority.IMPORTANT


class CaseQuestionResponse(BaseModel):
    id: str
    case_id: str
    question: str
    context: str | None
    category: str
    priority: QuestionPriority
    generated_by: str
    status: QuestionStatus
    answer: str | None
    answered_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class AnswerQuestionRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=4000)


class DismissQuestionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
