"""Evidence and timeline schemas."""

from datetime import datetime

from pydantic import BaseModel


class EvidenceCreate(BaseModel):
    title: str
    description: str | None = None
    evidence_type: str  # email, screenshot, document, receipt, correspondence, policy, note, contract
    source_reference: str | None = None
    content: str | None = None  # For text-based evidence
    tags: list[str] | None = None
    event_date: str | None = None


class EvidenceResponse(BaseModel):
    id: str
    case_id: str
    title: str
    description: str | None
    evidence_type: str
    source_reference: str | None
    file_path: str | None
    content: str | None
    extracted_snippets: list[dict] | None
    tags: list[str] | None
    collected_by: str
    event_date: str | None
    unanswered_questions: list[str] | None
    source_request_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TimelineEventCreate(BaseModel):
    event_date: str
    description: str
    evidence_ids: list[str] | None = None
    source: str | None = None
    event_type: str | None = None  # incident, communication, deadline, action


class TimelineEventResponse(BaseModel):
    id: str
    case_id: str
    event_date: str
    description: str
    evidence_ids: list[str] | None
    source: str | None
    event_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DraftCreate(BaseModel):
    draft_type: str  # email, letter, complaint, memo, question
    title: str
    content: str
    recipient: str | None = None
    tone: str = "professional"


class DraftResponse(BaseModel):
    id: str
    case_id: str
    draft_type: str
    title: str
    content: str
    recipient: str | None
    tone: str
    status: str
    generated_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
